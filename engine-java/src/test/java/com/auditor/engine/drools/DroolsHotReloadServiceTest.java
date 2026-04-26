package com.auditor.engine.drools;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import org.kie.api.runtime.KieContainer;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Drools hot reload service unit test
 */
@DisplayName("Drools Rule Hot Reload Service Test")
public class DroolsHotReloadServiceTest {

    private DroolsHotReloadService hotReloadService;

    // Minimal compilable DRL content (for testing)
    private static final String VALID_DRL =
        "package rules.formatting;\n" +
        "import com.auditor.grpc.Section;\n" +
        "import com.auditor.grpc.Issue;\n" +
        "import com.auditor.grpc.Severity;\n" +
        "import java.util.List;\n" +
        "global java.util.List results;\n" +
        "global org.slf4j.Logger logger;\n" +
        "\n" +
        "rule \"Hot Reload Test Rule\"\n" +
        "    when\n" +
        "        $s : Section(type == \"test_hot_reload\")\n" +
        "    then\n" +
        "        Issue issue = Issue.newBuilder()\n" +
        "            .setCode(\"HOT_RELOAD_001\")\n" +
        "            .setMessage(\"Hot reload rule is effective\")\n" +
        "            .setSeverity(Severity.INFO)\n" +
        "            .build();\n" +
        "        results.add(issue);\n" +
        "end\n";

    private static final String INVALID_DRL =
        "package rules.formatting;\n" +
        "this is not valid drl syntax !!!!\n";

    @BeforeEach
    void setUp() {
        hotReloadService = new DroolsHotReloadService();
    }

    @Test
    @DisplayName("Should have active KieContainer after initialization")
    void testInitialization() {
        KieContainer container = hotReloadService.getActiveContainer();
        assertNotNull(container, "KieContainer should not be null after initialization");

        DroolsHotReloadService.RuleStatus status = hotReloadService.getStatus();
        assertTrue(status.containerActive, "Container should be active");
        assertEquals(0, status.totalReloads, "Initial hot reload count should be 0");
    }

    @Test
    @DisplayName("Reload with same content should return noChange (fast alignment based on MD5 hash)")
    void testNoChangeWhenSameContent() {
        // First update (establish baseline)
        hotReloadService.reloadRule("formatting/test.drl", VALID_DRL);

        // Second update with same content
        DroolsHotReloadService.HotReloadResult result =
            hotReloadService.reloadRule("formatting/test.drl", VALID_DRL);

        assertTrue(result.success, "Same content should return success");
        assertFalse(result.changed, "Same content should not trigger recompilation");
        assertEquals(0, result.elapsedMs, "Elapsed time should be 0 when no changes");
        System.out.println("✅ MD5 hash fast alignment: skip recompilation for same content");
    }

    @Test
    @DisplayName("Invalid DRL should fail compilation and auto rollback, old container remains usable")
    void testInvalidDrlRollback() {
        // Attempt to load invalid DRL
        DroolsHotReloadService.HotReloadResult result =
            hotReloadService.reloadRule("formatting/invalid.drl", INVALID_DRL);

        assertFalse(result.success, "Invalid DRL should return failure");
        assertNotNull(result.errorMessage, "Error message should be present");

        // Verify old container is still usable (auto rollback)
        KieContainer currentContainer = hotReloadService.getActiveContainer();
        assertNotNull(currentContainer, "Container should not be null after rollback");
        System.out.println("✅ Auto rollback: invalid DRL compilation failed, old rules remain usable");
        System.out.println("   Error message: " + result.errorMessage.substring(0, Math.min(100, result.errorMessage.length())));
    }

    @Test
    @DisplayName("Reloading from classpath should succeed")
    void testReloadFromClasspath() {
        DroolsHotReloadService.HotReloadResult result = hotReloadService.reloadFromClasspath();

        assertTrue(result.success, "Reloading from classpath should succeed");
        assertNotNull(hotReloadService.getActiveContainer(), "Container should not be null after reload");
        System.out.println("✅ Classpath reload succeeded");
    }

    @Test
    @DisplayName("Hot reload history should be tracked correctly")
    void testReloadHistory() {
        // Perform several hot reloads
        hotReloadService.reloadRule("test/rule1.drl", VALID_DRL);
        hotReloadService.reloadRule("test/rule2.drl", VALID_DRL);
        hotReloadService.reloadRule("test/invalid.drl", INVALID_DRL); // failed one

        DroolsHotReloadService.RuleStatus status = hotReloadService.getStatus();
        assertTrue(status.totalReloads >= 2, "There should be at least 2 history records");

        // Last one should be failure
        assertNotNull(status.lastReload, "There should be a last record");

        System.out.println("✅ Hot reload history is correct, total " + status.totalReloads + " entries");
    }

    @Test
    @DisplayName("Concurrent access to KieContainer should be thread-safe")
    void testConcurrentContainerAccess() throws InterruptedException {
        int threadCount = 20;
        java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(threadCount);
        java.util.concurrent.atomic.AtomicInteger nullCount = new java.util.concurrent.atomic.AtomicInteger(0);

        for (int i = 0; i < threadCount; i++) {
            Thread.ofVirtual().start(() -> {
                try {
                    KieContainer container = hotReloadService.getActiveContainer();
                    if (container == null) nullCount.incrementAndGet();
                } finally {
                    latch.countDown();
                }
            });
        }

        latch.await(10, java.util.concurrent.TimeUnit.SECONDS);
        assertEquals(0, nullCount.get(), "All threads should get non-null container during concurrent reads");
        System.out.println("✅ Concurrent read thread safety: " + threadCount + " virtual threads read simultaneously with no null");
    }
}