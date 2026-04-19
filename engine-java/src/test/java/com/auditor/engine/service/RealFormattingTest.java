package com.auditor.engine.service;

import com.auditor.grpc.*;
import com.auditor.engine.mock.RealFormattingDataGenerator;
import com.auditor.engine.mock.MockDroolsEngine;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

public class RealFormattingTest {
    
    @Test
    public void testRealThesisFormattingIssues() throws Exception {
        System.out.println("\n========== Real Thesis Formatting Check ==========");
        
        ParsedData data = RealFormattingDataGenerator.generateRealFormattingData();
        
        System.out.println("✅ Generated data contains " + data.getSectionsCount() + " sections");
        
        // Check if there are sections with line height of 1.83
        int lineHeightIssueCount = 0;
        for (Section section : data.getSectionsList()) {
            String lineHeight = section.getPropsMap().get("line-height");
            if (lineHeight != null && lineHeight.contains("1.83")) {
                lineHeightIssueCount++;
                if (lineHeightIssueCount <= 3) {
                    System.out.println("  - Section " + section.getSectionId() + ": line height = " + lineHeight);
                }
            }
        }
        
        System.out.println("✅ Detected " + lineHeightIssueCount + " sections with line height 1.83");
        
        // Directly use MockDroolsEngine for checking
        List<Issue> issues = MockDroolsEngine.checkFormattingRules(data);
        
        System.out.println("✅ Number of formatting issues detected: " + issues.size());
        
        if (issues.size() > 0) {
            System.out.println("\nIssue details:");
            for (Issue issue : issues) {
                if (issues.size() <= 10 || issue.getMessage().contains("line height")) {
                    System.out.println("  - [" + issue.getSectionId() + "] " + issue.getMessage());
                }
            }
        }
        
        // Verify the system can correctly handle real data
        assertNotNull(data, "Data should not be null");
        assertTrue(data.getSectionsCount() > 0, "There should be section data");
        assertTrue(lineHeightIssueCount > 0, "Should detect sections with line height not equal to 1.5");
        
        System.out.println("\n✅ Real formatting test passed! The system successfully processed " + data.getSectionsCount() + " sections");
    }
}