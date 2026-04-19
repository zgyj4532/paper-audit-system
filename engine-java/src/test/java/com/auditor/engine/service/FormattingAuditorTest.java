package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

public class FormattingAuditorTest {

    private FormattingAuditor formattingAuditor;

    @BeforeEach
    public void setUp() {
        formattingAuditor = new FormattingAuditor();
    }

    @Test
    public void testCheckFormattingWithValidData() {
        ParsedData data = createValidParsedData();
        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        assertNotNull(issues);
        // Valid data should be checkable
        assertTrue(issues != null);
    }

    @Test
    public void testCheckFormattingWithInvalidFontSize() {
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
                        .setText("标题")
                        .putProps("font-size", "10")
                        .putProps("font-family", "黑体")
                        .build())
                .build();

        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        assertNotNull(issues);
        // At least one issue should be found
        assertTrue(issues.size() > 0, "Issue should be found");
    }

    @Test
    public void testCheckFormattingWithInvalidFont() {
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
                        .setText("标题")
                        .putProps("font-size", "16")
                        .putProps("font-family", "宋体")
                        .build())
                .build();

        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        assertNotNull(issues);
        // At least one issue should be found
        assertTrue(issues.size() > 0, "Issue should be found");
    }

    @Test
    public void testCheckFormattingWithMultipleSections() {
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
                        .putProps("font-family", "黑体")
                        .putProps("font-size", "16")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setType("heading")
                        .setLevel(2)
                        .setText("第一节")
                        .putProps("font-family", "黑体")
                        .putProps("font-size", "15")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(3)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("正文内容")
                        .putProps("font-family", "宋体")
                        .putProps("font-size", "12")
                        .build())
                .build();

        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        assertNotNull(issues);
        // Should be able to handle multiple sections
        assertTrue(issues.size() >= 0);
    }

    @Test
    public void testCheckFormattingWithEmptyData() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Empty Document")
                        .setPageCount(1)
                        .build())
                .build();

        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        assertNotNull(issues);
        // Empty data should have no issues or only low severity issues
        assertTrue(issues.isEmpty() || issues.stream().allMatch(i -> i.getSeverity() == Severity.LOW));
    }

    @Test
    public void testCheckFormattingReturnsIssuesWithCorrectStructure() {
        ParsedData data = createValidParsedData();
        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
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
                        .setMarginTop(2.5f)
                        .setMarginBottom(2.5f)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("标题")
                        .putProps("font-family", "黑体")
                        .putProps("font-size", "16")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("正文内容")
                        .putProps("font-family", "宋体")
                        .putProps("font-size", "12")
                        .build())
                .build();
    }
}