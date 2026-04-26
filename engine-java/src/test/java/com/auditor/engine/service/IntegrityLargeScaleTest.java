package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.Test;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Integrity module large-scale logic stress test
 * Simulate 200 sets of document samples to verify the robustness of the Drools rule engine
 */
public class IntegrityLargeScaleTest {

    @Test
    public void testIntegrityWith200Samples() throws IOException {
        IntegrityScanner scanner = new IntegrityScanner();
        List<Issue> allDetectedIssues = new ArrayList<>();
        
        System.out.println(">>> Starting integrity module 200 sample tests...");

        for (int i = 1; i <= 200; i++) {
            ParsedData.Builder docBuilder = ParsedData.newBuilder()
                    .setDocId("BATCH-TEST-" + i)
                    .setMetadata(DocumentMetadata.newBuilder()
                            .setTitle("Large-scale test sample No. " + i)
                            .setPageCount(i % 50 + 1) // Simulate different page counts
                            .build());

            // --- Inject 13 different logical errors in a loop ---
            
            if (i % 4 == 1) { 
                // Mode 1: Fatal missing (REQ) - only chapter one, missing abstract, introduction, conclusion, references
                docBuilder.addSections(createSection(1, "Chapter One Introduction", 1));
            } 
            else if (i % 4 == 2) { 
                // Mode 2: Title hierarchy conflict (HIER) - level 1 directly jumps to level 3
                docBuilder.addSections(createSection(1, "Abstract", 1));
                docBuilder.addSections(createSection(2, "1.1.1 Some Background", 3)); 
            }
            else if (i % 4 == 3) {
                // Mode 3: Duplication error (DUPLICATE) - duplicate ID
                docBuilder.addSections(createSection(1, "Abstract", 1));
                docBuilder.addSections(createSection(1, "Duplicate Abstract", 1));
            }
            else {
                // Mode 4: Incomplete metadata or boundary cases
                docBuilder.addSections(createSection(1, "Main Content", 0)); // paragraph without level
            }

            // Execute Drools audit
            List<Issue> currentIssues = scanner.scanIntegrity(docBuilder.build());
            allDetectedIssues.addAll(currentIssues);
        }

        // Write detailed summary of 200 tests to TXT file
        writeReportToTxt(allDetectedIssues);

        System.out.println(">>> Test completed!");
        System.out.println(">>> Total audited samples: 200");
        System.out.println(">>> Total issues found by rule engine: " + allDetectedIssues.size());
        System.out.println(">>> Report generated at: services/engine-java/target/integrity_audit_detail.txt");
    }

    private Section createSection(int id, String text, int level) {
        return Section.newBuilder()
                .setSectionId(id)
                .setText(text)
                .setType(level > 0 ? "heading" : "paragraph")
                .setLevel(level)
                .build();
    }

    private void writeReportToTxt(List<Issue> issues) throws IOException {
        File targetDir = new File("target");
        if (!targetDir.exists()) targetDir.mkdirs();

        String filePath = "target/integrity_audit_detail.txt";
        try (PrintWriter writer = new PrintWriter(new FileWriter(filePath))) {
            writer.println("Integrity Module Large-Scale Audit Detailed Report");
            writer.println("Test Time: " + LocalDateTime.now());
            writer.println("Total Samples: 200 sets");
            writer.println("==================================================");
            
            for (int i = 0; i < issues.size(); i++) {
                Issue issue = issues.get(i);
                writer.printf("[%03d] Code: %-15s | Severity: %-8s | Msg: %s%n", 
                    i + 1,
                    issue.getCode(),
                    issue.getSeverity(),
                    issue.getMessage());
            }
            writer.println("==================================================");
            writer.println("End of Report - Total " + issues.size() + " records");
        }
    }
}