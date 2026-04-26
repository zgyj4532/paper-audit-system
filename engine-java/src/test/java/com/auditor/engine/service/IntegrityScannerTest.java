package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

public class IntegrityScannerTest {

    private IntegrityScanner integrityScanner;

    @BeforeEach
    public void setUp() {
        integrityScanner = new IntegrityScanner();
    }

    @Test
    public void testScanIntegrityWithValidData() {
        ParsedData data = createValidParsedData();
        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        assertNotNull(issues);
        assertTrue(issues.stream().allMatch(i -> i.getSeverity() != Severity.CRITICAL));
    }

    @Test
    public void testScanIntegrityWithMissingChapters() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("第一章")
                        .build())
                .build();

        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        assertNotNull(issues);
        assertTrue(issues.size() > 0, "Should detect missing required chapters");
        assertTrue(issues.stream().anyMatch(i -> i.getCode().contains("REQ")), 
                   "Should have REQ related issues");
    }

    @Test
    public void testScanIntegrityWithCompleteStructure() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("摘要")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setType("heading")
                        .setLevel(1)
                        .setText("引言")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(3)
                        .setType("heading")
                        .setLevel(1)
                        .setText("正文")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(4)
                        .setType("heading")
                        .setLevel(1)
                        .setText("结论")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(5)
                        .setType("heading")
                        .setLevel(1)
                        .setText("参考文献")
                        .build())
                .build();

        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        assertNotNull(issues);
        assertFalse(issues.stream().anyMatch(i -> i.getCode().contains("REQ")), 
                    "Should not have missing required chapters issues");
    }

    @Test
    public void testScanIntegrityWithInvalidHeadingHierarchy() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("第一章")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setType("heading")
                        .setLevel(3)
                        .setText("第一节")
                        .build())
                .build();

        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        assertNotNull(issues);
        assertTrue(issues.stream().anyMatch(i -> i.getCode().contains("HIER")), 
                   "Should detect heading hierarchy issues");
    }

    @Test
    public void testScanIntegrityWithDuplicateHeadings() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("第一章")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("第二章")
                        .build())
                .build();

        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        assertNotNull(issues);
        assertTrue(issues.stream().anyMatch(i -> i.getCode().contains("DUPLICATE")), 
                   "Should detect duplicate chapter issues");
    }

    @Test
    public void testScanIntegrityReturnsIssuesWithCorrectStructure() {
        ParsedData data = createValidParsedData();
        List<Issue> issues = integrityScanner.scanIntegrity(data);
        
        for (Issue issue : issues) {
            assertNotNull(issue.getCode(), "Issue code cannot be null");
            assertNotNull(issue.getMessage(), "Issue message cannot be null");
            assertNotNull(issue.getSeverity(), "Issue severity cannot be null");
        }
    }

    private ParsedData createValidParsedData() {
        return ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("摘要")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setType("heading")
                        .setLevel(1)
                        .setText("引言")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(3)
                        .setType("heading")
                        .setLevel(1)
                        .setText("正文")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(4)
                        .setType("heading")
                        .setLevel(1)
                        .setText("结论")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(5)
                        .setType("heading")
                        .setLevel(1)
                        .setText("参考文献")
                        .build())
                .build();
    }
}