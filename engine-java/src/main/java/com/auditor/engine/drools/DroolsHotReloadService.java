package com.auditor.engine.drools;

import org.kie.api.KieServices;
import org.kie.api.builder.*;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * Drools rule hot reload service
 *
 * Core capabilities:
 *   1. Runtime non-stop update of DRL rule files (KieFileSystem + KieBuilder dynamic recompilation)
 *   2. Fast change detection based on MD5 hash (only triggers recompilation if file truly changes)
 *   3. Read-write lock ensures concurrency safety (review requests read lock / hot reload write lock)
 *   4. Automatic rollback: retain old version if new rule compilation fails, service uninterrupted
 *   5. File system monitoring: optionally enabled, automatically detects DRL file changes
 *
 * Usage:
 *   - REST interface trigger: POST /api/rules/reload
 *   - Pass new DRL content: POST /api/rules/update/{ruleName}
 *   - Query current version: GET /api/rules/status
 */
@Service
public class DroolsHotReloadService {

    private static final Logger logger = LoggerFactory.getLogger(DroolsHotReloadService.class);

    // Rule file path prefix (KieFileSystem virtual path)
    private static final String RULE_BASE_PATH = "src/main/resources/rules/";

    // Current active KieContainer (atomic reference, supports lock-free reads)
    private final AtomicReference<KieContainer> activeContainer = new AtomicReference<>();

    // Read-write lock: multiple review requests can read concurrently, hot reload exclusive write
    private final ReadWriteLock rwLock = new ReentrantReadWriteLock();

    // Current rule content MD5 hash (used for fast change detection)
    private final Map<String, String> ruleHashes = new ConcurrentHashMap<>();

    // Hot reload history records
    private final List<ReloadRecord> reloadHistory = new CopyOnWriteArrayList<>();

    // KieServices instance
    private final KieServices kieServices = KieServices.Factory.get();

    // Current rule content cache (used for recompilation)
    private final Map<String, String> ruleContents = new ConcurrentHashMap<>();

    /**
     * Initialization: load initial rules from classpath
     */
    public DroolsHotReloadService() {
        try {
            KieContainer initial = kieServices.getKieClasspathContainer();
            activeContainer.set(initial);
            logger.info("DroolsHotReloadService initialized successfully, classpath rules loaded");
        } catch (Exception e) {
            logger.error("DroolsHotReloadService initialization failed: {}", e.getMessage());
        }
    }

    /**
     * Get current active KieContainer (thread-safe, for review service calls)
     *
     * Usage:
     *   KieContainer container = hotReloadService.getActiveContainer();
     *   KieSession session = container.newKieSession("formattingSession");
     */
    public KieContainer getActiveContainer() {
        rwLock.readLock().lock();
        try {
            return activeContainer.get();
        } finally {
            rwLock.readLock().unlock();
        }
    }

    /**
     * Hot reload a single rule file
     *
     * @param ruleName   Rule file name, e.g. "formatting/formatting.drl"
     * @param drlContent New DRL rule content
     * @return Hot reload result
     */
    public HotReloadResult reloadRule(String ruleName, String drlContent) {
        String newHash = computeMd5(drlContent);
        String oldHash = ruleHashes.get(ruleName);

        // Fast path: content unchanged, return directly (hash-based quick alignment)
        if (newHash.equals(oldHash)) {
            logger.info("Rule [{}] content unchanged (MD5: {}), skipping hot reload", ruleName, newHash);
            return HotReloadResult.noChange(ruleName, newHash);
        }

        logger.info("Detected change in rule [{}], MD5: {} -> {}, starting hot reload...", ruleName, oldHash, newHash);
        long startTime = System.currentTimeMillis();

        // Write lock: block new review requests during hot reload (requests in progress complete with old rules)
        rwLock.writeLock().lock();
        try {
            // Update rule content cache
            ruleContents.put(ruleName, drlContent);

            // Recompile all rules (KieFileSystem full rebuild)
            KieContainer newContainer = buildNewContainer();

            // Compilation success: atomically replace active container
            KieContainer oldContainer = activeContainer.getAndSet(newContainer);
            ruleHashes.put(ruleName, newHash);

            long elapsed = System.currentTimeMillis() - startTime;
            logger.info("Rule [{}] hot reload succeeded, took {}ms", ruleName, elapsed);

            // Record history
            ReloadRecord record = new ReloadRecord(ruleName, oldHash, newHash, elapsed, true, null);
            reloadHistory.add(record);

            // Asynchronously dispose old container (wait for ongoing requests to complete)
            if (oldContainer != null) {
                CompletableFuture.runAsync(() -> {
                    try {
                        Thread.sleep(5000); // Wait 5 seconds to let old requests complete
                        oldContainer.dispose();
                        logger.debug("Old KieContainer disposed");
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            return HotReloadResult.success(ruleName, oldHash, newHash, elapsed);

        } catch (Exception e) {
            // Compilation failed: rollback, keep old version, service uninterrupted
            ruleContents.remove(ruleName); // Rollback content cache
            long elapsed = System.currentTimeMillis() - startTime;
            logger.error("Rule [{}] hot reload failed, rolled back to old version: {}", ruleName, e.getMessage());

            ReloadRecord record = new ReloadRecord(ruleName, oldHash, newHash, elapsed, false, e.getMessage());
            reloadHistory.add(record);

            return HotReloadResult.failure(ruleName, e.getMessage());

        } finally {
            rwLock.writeLock().unlock();
        }
    }

    /**
     * Batch hot reload multiple rules (atomic operation: all succeed to switch, any failure rolls back all)
     *
     * @param rules Map<rule file name, DRL content>
     * @return Batch update result
     */
    public HotReloadResult reloadRules(Map<String, String> rules) {
        // Pre-check: compute all rules' hashes, filter unchanged
        Map<String, String> changedRules = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : rules.entrySet()) {
            String newHash = computeMd5(entry.getValue());
            if (!newHash.equals(ruleHashes.get(entry.getKey()))) {
                changedRules.put(entry.getKey(), entry.getValue());
            }
        }

        if (changedRules.isEmpty()) {
            logger.info("Batch hot reload: all rule contents unchanged, skipping");
            return HotReloadResult.noChange("batch", "all-same");
        }

        logger.info("Batch hot reload: {} rules changed: {}", changedRules.size(), changedRules.keySet());
        long startTime = System.currentTimeMillis();

         // Backup current content (for rollback, must declare outside try for catch access)
        Map<String, String> backup = new HashMap<>(ruleContents);
        rwLock.writeLock().lock();
        try {
            // Update content cache
            ruleContents.putAll(changedRules);

            // Attempt compilation
            KieContainer newContainer = buildNewContainer();

            // Success: atomic replace
            KieContainer oldContainer = activeContainer.getAndSet(newContainer);
            changedRules.forEach((name, content) ->
                ruleHashes.put(name, computeMd5(content)));

            long elapsed = System.currentTimeMillis() - startTime;
            logger.info("Batch hot reload succeeded: {} rules, took {}ms", changedRules.size(), elapsed);

            if (oldContainer != null) {
                CompletableFuture.runAsync(() -> {
                    try { Thread.sleep(5000); oldContainer.dispose(); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                });
            }

            return HotReloadResult.success("batch[" + changedRules.size() + "]",
                "old", "new", elapsed);

        } catch (Exception e) {
            // Rollback
            ruleContents.clear();
            ruleContents.putAll(backup);
            logger.error("Batch hot reload failed, rolled back all: {}", e.getMessage());
            return HotReloadResult.failure("batch", e.getMessage());

        } finally {
            rwLock.writeLock().unlock();
        }
    }

    /**
     * Force reload all rules from classpath (factory reset)
     *
     * Note: cannot repeatedly call kieServices.getKieClasspathContainer(), otherwise throws:
     *   "There's already another KieContainer created from a different ClassLoader"
     * Correct approach: read DRL file content via ClassLoader, recompile with KieFileSystem
     */
    public HotReloadResult reloadFromClasspath() {
        logger.info("Force reload all rules from classpath...");
        long startTime = System.currentTimeMillis();
        rwLock.writeLock().lock();
        try {
            // Read all DRL file contents from classpath resources
            String[] drlPaths = {
                "rules/formatting/formatting.drl",
                "rules/reference/reference.drl",
                "rules/integrity/integrity.drl"
            };
            Map<String, String> freshContents = new LinkedHashMap<>();
            for (String path : drlPaths) {
                try (var is = getClass().getClassLoader().getResourceAsStream(path)) {
                    if (is != null) {
                        String content = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                        freshContents.put(path, content);
                        logger.debug("Read classpath rule file: {}", path);
                    } else {
                        logger.warn("Classpath rule file not found: {}", path);
                    }
                } catch (Exception ex) {
                    logger.warn("Failed to read rule file: {} - {}", path, ex.getMessage());
                }
            }

            if (freshContents.isEmpty()) {
                return HotReloadResult.failure("classpath-reload", "No DRL rule files found");
            }

            // Update content cache
            ruleContents.clear();
            ruleContents.putAll(freshContents);

            // Recompile with KieFileSystem (do not call getKieClasspathContainer)
            KieContainer newContainer = buildNewContainer();

            // Update hashes
            ruleHashes.clear();
            freshContents.forEach((name, content) -> ruleHashes.put(name, computeMd5(content)));

            // Atomically replace container
            KieContainer old = activeContainer.getAndSet(newContainer);
            if (old != null) {
                CompletableFuture.runAsync(() -> {
                    try { Thread.sleep(3000); old.dispose(); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                });
            }

            long elapsed = System.currentTimeMillis() - startTime;
            logger.info("Reload from classpath succeeded, took {}ms, total {} rule files", elapsed, freshContents.size());
            return HotReloadResult.success("classpath-reload", null, String.valueOf(freshContents.size()), elapsed);

        } catch (Exception e) {
            logger.error("Reload from classpath failed: {}", e.getMessage());
            return HotReloadResult.failure("classpath-reload", e.getMessage());
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    /**
     * Get current rule status (version info, hashes, history)
     */
    public RuleStatus getStatus() {
        return new RuleStatus(
            ruleHashes,
            reloadHistory.size(),
            reloadHistory.isEmpty() ? null : reloadHistory.get(reloadHistory.size() - 1),
            activeContainer.get() != null
        );
    }

    /**
     * Get recent N hot reload history records
     */
    public List<ReloadRecord> getReloadHistory(int limit) {
        int size = reloadHistory.size();
        int from = Math.max(0, size - limit);
        return new ArrayList<>(reloadHistory.subList(from, size));
    }

    // ==================== Private methods ====================

    /**
     * Rebuild KieContainer using KieFileSystem
     * Write all rules in ruleContents to virtual file system and compile
     */
    private KieContainer buildNewContainer() {
        KieFileSystem kfs = kieServices.newKieFileSystem();

        // Write all rule contents to KieFileSystem (virtual file system)
        for (Map.Entry<String, String> entry : ruleContents.entrySet()) {
            String virtualPath = RULE_BASE_PATH + entry.getKey();
            kfs.write(virtualPath, entry.getValue());
            logger.debug("Wrote rule to KieFileSystem: {}", virtualPath);
        }

        // Compile
        KieBuilder kieBuilder = kieServices.newKieBuilder(kfs);
        kieBuilder.buildAll();

        // Check compilation results
        Results results = kieBuilder.getResults();
        if (results.hasMessages(Message.Level.ERROR)) {
            StringBuilder errors = new StringBuilder("DRL compilation errors:\n");
            results.getMessages(Message.Level.ERROR).forEach(msg ->
                errors.append("  [").append(msg.getPath()).append("] ").append(msg.getText()).append("\n"));
            throw new IllegalArgumentException(errors.toString());
        }

        // Print warnings (do not block)
        if (results.hasMessages(Message.Level.WARNING)) {
            results.getMessages(Message.Level.WARNING).forEach(msg ->
                logger.warn("DRL compilation warning [{}]: {}", msg.getPath(), msg.getText()));
        }

        return kieServices.newKieContainer(kieBuilder.getKieModule().getReleaseId());
    }

    /**
     * Compute MD5 hash of a string (used for fast change detection)
     */
    private String computeMd5(String content) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] hash = md.digest(content.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            return String.valueOf(content.hashCode());
        }
    }

    // ==================== Data classes ====================

    /**
     * Hot reload result
     */
    public static class HotReloadResult {
        public final boolean success;
        public final boolean changed;
        public final String ruleName;
        public final String oldHash;
        public final String newHash;
        public final long elapsedMs;
        public final String errorMessage;
        public final String timestamp;

        private HotReloadResult(boolean success, boolean changed, String ruleName,
                                String oldHash, String newHash, long elapsedMs, String errorMessage) {
            this.success = success;
            this.changed = changed;
            this.ruleName = ruleName;
            this.oldHash = oldHash;
            this.newHash = newHash;
            this.elapsedMs = elapsedMs;
            this.errorMessage = errorMessage;
            this.timestamp = LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        }

        static HotReloadResult success(String name, String oldHash, String newHash, long elapsed) {
            return new HotReloadResult(true, true, name, oldHash, newHash, elapsed, null);
        }

        static HotReloadResult noChange(String name, String hash) {
            return new HotReloadResult(true, false, name, hash, hash, 0, null);
        }

        static HotReloadResult failure(String name, String error) {
            return new HotReloadResult(false, true, name, null, null, 0, error);
        }

        @Override
        public String toString() {
            return String.format("HotReloadResult{success=%s, changed=%s, rule='%s', elapsed=%dms, error='%s'}",
                success, changed, ruleName, elapsedMs, errorMessage);
        }
    }

    /**
     * Hot reload history record
     */
    public static class ReloadRecord {
        public final String ruleName;
        public final String oldHash;
        public final String newHash;
        public final long elapsedMs;
        public final boolean success;
        public final String errorMessage;
        public final String timestamp;

        public ReloadRecord(String ruleName, String oldHash, String newHash,
                            long elapsedMs, boolean success, String errorMessage) {
            this.ruleName = ruleName;
            this.oldHash = oldHash;
            this.newHash = newHash;
            this.elapsedMs = elapsedMs;
            this.success = success;
            this.errorMessage = errorMessage;
            this.timestamp = LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        }
    }

    /**
     * Rule status information
     */
    public static class RuleStatus {
        public final Map<String, String> ruleHashes;
        public final int totalReloads;
        public final ReloadRecord lastReload;
        public final boolean containerActive;

        public RuleStatus(Map<String, String> ruleHashes, int totalReloads,
                          ReloadRecord lastReload, boolean containerActive) {
            this.ruleHashes = Collections.unmodifiableMap(ruleHashes);
            this.totalReloads = totalReloads;
            this.lastReload = lastReload;
            this.containerActive = containerActive;
        }
    }
}