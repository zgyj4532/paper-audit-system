package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Accuracy test: 200 references, each with exactly 1 error
 * Used to calculate the true detection accuracy
 */
public class AccuracyTest200References {
    
    private static final Logger logger = LoggerFactory.getLogger(AccuracyTest200References.class);
    
    @Test
    public void testAccuracy200References() {
        // Generate 200 references, each with exactly 1 error
        List<Reference> references = generate200References();
        
        // Build ParsedData
        ParsedData data = ParsedData.newBuilder()
            .addAllReferences(references)
            .build();
        
        // Run check
        ReferenceChecker checker = new ReferenceChecker();
        List<Issue> issues = checker.checkReferences(data);
        
        // Count results
        int totalReferences = references.size();
        int detectedIssues = issues.size();
        
        // Calculate accuracy
        // Only count format errors (starting with ERR_), exclude warnings (starting with WARN_)
        int formatErrors = 0;
        for (Issue issue : issues) {
            if (issue.getCode().startsWith("ERR_")) {
                formatErrors++;
            }
        }
        
        // Accuracy = number of references with format errors / total references
        // Since each reference has only 1 error, accuracy = format error count / total references
        double accuracy = (formatErrors * 100.0) / totalReferences;
        
        logger.info("========== Accuracy Test Results ==========");
        logger.info("Total references: {}", totalReferences);
        logger.info("Format errors: {}", formatErrors);
        logger.info("Other issues: {}", detectedIssues - formatErrors);
        logger.info(String.format("Accuracy: %.2f%%", accuracy));
        logger.info("=====================================");
        
        // Print all detected issues
        logger.info("\nDetails of detected issues:");
        for (Issue issue : issues) {
            logger.info("✓ [{}] {}", issue.getCode(), issue.getMessage());
        }
        
        // Verify accuracy > 98%
        assertTrue(accuracy >= 98.0, 
            String.format("Accuracy %.2f%% < 98%%, detected issues %d < %d", 
                accuracy, detectedIssues, (int)(totalReferences * 0.98)));
    }
    
    /**
     * Generate 200 references, each with exactly 1 error
     * 
     * Error distribution:
     * - Journal [J]: 50 entries (10 for each error type)
     *   - Full-width comma: 10 entries
     *   - Year out of range: 10 entries
     *   - No period after [J]: 10 entries
     *   - Missing volume and issue: 10 entries
     *   - Missing page numbers: 10 entries
     * - Monograph [M]: 50 entries (10 for each error type)
     *   - Full-width period: 10 entries
     *   - Year out of range: 10 entries
     *   - No period after [M]: 10 entries
     *   - Missing place of publication: 10 entries
     *   - Missing publisher: 10 entries
     * - Thesis [D]: 50 entries (10 for each error type)
     *   - Full-width period: 10 entries
     *   - Year out of range: 10 entries
     *   - No period after [D]: 10 entries
     *   - Missing degree awarding institution: 10 entries
     *   - Missing year: 10 entries
     * - Conference Proceedings [C]: 50 entries (10 for each error type)
     *   - Full-width comma: 10 entries
     *   - Year out of range: 10 entries
     *   - No period after [C]: 10 entries
     *   - Missing conference location: 10 entries
     *   - Missing conference name: 10 entries
     */
    private static List<Reference> generate200References() {
        List<Reference> references = new ArrayList<>();
        int refId = 1;
        
        // ============ Journal [J] - 50 entries ============
        
        // Error 1: Full-width comma - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + "。论文题名[J]. 期刊名，2020, 10(1): 1-10.")
                .build());
            refId++;
        }
        
        // Error 2: Year out of range - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[J]. 期刊名, " + (2027 + i) + ", 10(1): 1-10.")
                .build());
            refId++;
        }
        
        // Error 3: No period after [J] - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[J] 期刊名, 2020, 10(1): 1-10.")
                .build());
            refId++;
        }
        
        // Error 4: Missing volume and issue - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[J]. 期刊名, 2020: 1-10.")
                .build());
            refId++;
        }
        
        // Error 5: Missing page numbers - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[J]. 期刊名, 2020, 10(1).")
                .build());
            refId++;
        }
        
        // ============ Monograph [M] - 50 entries ============
        
        // Error 6: Full-width period - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 书名[M]。北京: 出版社, 2020。")
                .build());
            refId++;
        }
        
        // Error 7: Year out of range - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 书名[M]. 北京: 出版社, " + (2050 + i) + ".")
                .build());
            refId++;
        }
        
        // Error 8: No period after [M] - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 书名[M] 北京: 出版社, 2020.")
                .build());
            refId++;
        }
        
        // Error 9: Missing place of publication - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 书名[M]. 出版社, 2020.")
                .build());
            refId++;
        }
        
        // Error 10: Missing publisher - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 书名[M]. 北京:, 2020.")
                .build());
            refId++;
        }
        
        // ============ Thesis [D] - 50 entries ============
        
        // Error 11: Full-width period - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[D]。北京: 清华大学, 2020。")
                .build());
            refId++;
        }
        
        // Error 12: Year out of range - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[D]. 北京: 清华大学, " + (2040 + i) + ".")
                .build());
            refId++;
        }
        
        // Error 13: No period after [D] - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[D] 北京: 清华大学, 2020.")
                .build());
            refId++;
        }
        
        // Error 14: Missing degree awarding institution - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[D]. 2020.")
                .build());
            refId++;
        }
        
        // Error 15: Missing year - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[D]. 北京: 清华大学.")
                .build());
            refId++;
        }
        
        // ============ Conference Proceedings [C] - 50 entries ============
        
        // Error 16: Full-width comma - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + "。论文题名[C]. 会议名，北京，2020.")
                .build());
            refId++;
        }
        
        // Error 17: Year out of range - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[C]. 会议名, 北京, " + (2099 + i) + ".")
                .build());
            refId++;
        }
        
        // Error 18: No period after [C] - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[C] 会议名, 北京, 2020.")
                .build());
            refId++;
        }
        
        // Error 19: Missing conference location - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[C]. 会议名, 2020.")
                .build());
            refId++;
        }
        
        // Error 20: Missing conference name - 10 entries
        for (int i = 0; i < 10; i++) {
            references.add(Reference.newBuilder()
                .setRefId("[" + refId + "]")
                .setRawText("[" + refId + "] 作者" + i + ". 论文题名[C]. 北京, 2020.")
                .build());
            refId++;
        }
        
        return references;
    }
}