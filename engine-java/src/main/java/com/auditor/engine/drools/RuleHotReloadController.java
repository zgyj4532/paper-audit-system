package com.auditor.engine.drools;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Drools Rule Hot Reload REST Controller
 *
 * Provides the following interfaces:
 *   GET  /api/rules/status              - Query current rule version and hot reload history
 *   POST /api/rules/reload              - Reload all rules from classpath (factory reset)
 *   POST /api/rules/update/{ruleName}   - Update a single rule (pass in new DRL content)
 *   POST /api/rules/update/batch        - Batch update multiple rules (atomic operation)
 *   GET  /api/rules/history             - Query the latest 20 hot reload histories
 *
 * Typical usage scenario (member B modifies rules without restarting the service):
 *   1. Modify local formatting.drl
 *   2. Call POST /api/rules/update/formatting/formatting.drl with new content
 *   3. The service switches to the new rules within < 500ms, ongoing requests are unaffected
 */
@RestController
@RequestMapping("/api/rules")
public class RuleHotReloadController {

    @Autowired
    private DroolsHotReloadService hotReloadService;

    /**
     * Query current rule status
     *
     * Response example:
     * {
     *   "containerActive": true,
     *   "totalReloads": 3,
     *   "ruleHashes": {
     *     "formatting/formatting.drl": "a1b2c3d4...",
     *     "reference/reference.drl": "e5f6g7h8..."
     *   },
     *   "lastReload": { "ruleName": "formatting/formatting.drl", "success": true, "elapsedMs": 312 }
     * }
     */
    @GetMapping("/status")
    public ResponseEntity<DroolsHotReloadService.RuleStatus> getStatus() {
        return ResponseEntity.ok(hotReloadService.getStatus());
    }

    /**
     * Reload all rules from classpath (factory reset)
     *
     * Use case: rule files have been deployed to the jar via CI/CD and need to be reloaded
     */
    @PostMapping("/reload")
    public ResponseEntity<DroolsHotReloadService.HotReloadResult> reloadFromClasspath() {
        DroolsHotReloadService.HotReloadResult result = hotReloadService.reloadFromClasspath();
        return result.success
            ? ResponseEntity.ok(result)
            : ResponseEntity.internalServerError().body(result);
    }

    /**
     * Update a single rule file (runtime hot reload)
     *
     * @param ruleName Rule file name (URL encoded), e.g. "formatting%2Fformatting.drl"
     * @param body     Request body containing "content" field (DRL file content)
     *
     * Request example:
     *   POST /api/rules/update/formatting%2Fformatting.drl
     *   Content-Type: application/json
     *   { "content": "package rules.formatting;\n\nrule \"Check Font\" ..." }
     *
     * Response example (success):
     *   { "success": true, "changed": true, "ruleName": "formatting/formatting.drl",
     *     "oldHash": "a1b2...", "newHash": "c3d4...", "elapsedMs": 312 }
     *
     * Response example (no content change):
     *   { "success": true, "changed": false, "ruleName": "...", "elapsedMs": 0 }
     *
     * Response example (compilation failure, auto rollback):
     *   { "success": false, "errorMessage": "DRL compilation error: ..." }
     */
    @PostMapping("/update/{ruleName}")
    public ResponseEntity<DroolsHotReloadService.HotReloadResult> updateRule(
            @PathVariable String ruleName,
            @RequestBody Map<String, String> body) {

        String content = body.get("content");
        if (content == null || content.isBlank()) {
            return ResponseEntity.badRequest().body(
                DroolsHotReloadService.HotReloadResult.failure(ruleName, "Missing 'content' field in request body"));
        }

        // URL decode rule name (supporting / in path)
        String decodedName = ruleName.replace("%2F", "/").replace("%2f", "/");

        DroolsHotReloadService.HotReloadResult result = hotReloadService.reloadRule(decodedName, content);
        return result.success
            ? ResponseEntity.ok(result)
            : ResponseEntity.internalServerError().body(result);
    }

    /**
     * Batch update multiple rules (atomic operation: switch only if all succeed, rollback all if any fail)
     *
     * Request example:
     *   POST /api/rules/update/batch
     *   Content-Type: application/json
     *   {
     *     "formatting/formatting.drl": "package rules.formatting; ...",
     *     "reference/reference.drl": "package rules.reference; ..."
     *   }
     */
    @PostMapping("/update/batch")
    public ResponseEntity<DroolsHotReloadService.HotReloadResult> updateRulesBatch(
            @RequestBody Map<String, String> rules) {

        if (rules == null || rules.isEmpty()) {
            return ResponseEntity.badRequest().body(
                DroolsHotReloadService.HotReloadResult.failure("batch", "Request body cannot be empty"));
        }

        DroolsHotReloadService.HotReloadResult result = hotReloadService.reloadRules(rules);
        return result.success
            ? ResponseEntity.ok(result)
            : ResponseEntity.internalServerError().body(result);
    }

    /**
     * Query the latest 20 hot reload histories
     */
    @GetMapping("/history")
    public ResponseEntity<List<DroolsHotReloadService.ReloadRecord>> getHistory(
            @RequestParam(defaultValue = "20") int limit) {
        return ResponseEntity.ok(hotReloadService.getReloadHistory(Math.min(limit, 100)));
    }
}