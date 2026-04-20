package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

public class ReferenceCheckerTest {

    private ReferenceChecker referenceChecker;

    @BeforeEach
    public void setUp() {
        referenceChecker = new ReferenceChecker();
    }

    @Test
    public void testCheckReferencesWithValidData() {
        ParsedData data = createValidParsedDataWithReferences();
        List<Issue> issues = referenceChecker.checkReferences(data);
        
        assertNotNull(issues);
        // Valid data should have no CRITICAL level issues
        assertFalse(issues.stream().anyMatch(i -> i.getSeverity() == Severity.CRITICAL));
    }

    @Test
    public void testCheckReferencesWithMissingReferences() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("根据研究[1]表明...")
                        .build())
                .build();

        List<Issue> issues = referenceChecker.checkReferences(data);
        
        assertNotNull(issues);
        // Should detect missing reference issues
        assertTrue(issues.size() > 0, "Should detect missing reference issues");
    }

    @Test
    public void testCheckReferencesWithValidReferences() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("根据研究[1]表明...")
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[1]")
                        .setRawText("张三, 李四. 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                        .setIsValidFormat(true)
                        .build())
                .build();

        List<Issue> issues = referenceChecker.checkReferences(data);
        
        assertNotNull(issues);
        // Valid references should have no CRITICAL issues
        assertFalse(issues.stream().anyMatch(i -> i.getSeverity() == Severity.CRITICAL));
    }

    @Test
    public void testCheckReferencesWithMultipleReferences() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("根据研究[1]和[2]表明...")
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[1]")
                        .setRawText("张三, 李四. 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                        .setIsValidFormat(true)
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[2]")
                        .setRawText("王五, 赵六. 论文题名[J]. 期刊名, 2022, 8(1): 20-28.")
                        .setIsValidFormat(true)
                        .build())
                .build();

        List<Issue> issues = referenceChecker.checkReferences(data);
        
        assertNotNull(issues);
        // Multiple valid references should have no CRITICAL issues
        assertFalse(issues.stream().anyMatch(i -> i.getSeverity() == Severity.CRITICAL));
    }

    @Test
    public void testCheckReferencesWithUnusedReferences() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("根据研究[1]表明...")
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[1]")
                        .setRawText("Author1. Title1. Journal1, 2023.")
                        .setIsValidFormat(true)
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[2]")
                        .setRawText("Author2. Title2. Journal2, 2023.")
                        .setIsValidFormat(true)
                        .build())
                .build();

        List<Issue> issues = referenceChecker.checkReferences(data);
        
        assertNotNull(issues);
        // Should detect at least one issue (unused reference)
        assertTrue(issues.size() > 0, "Should detect issues");
    }

    @Test
    public void testCheckReferencesReturnsIssuesWithCorrectStructure() {
        ParsedData data = createValidParsedDataWithReferences();
        List<Issue> issues = referenceChecker.checkReferences(data);
        
        for (Issue issue : issues) {
            assertNotNull(issue.getCode(), "Issue code cannot be null");
            assertNotNull(issue.getMessage(), "Issue message cannot be null");
            assertNotNull(issue.getSeverity(), "Issue severity cannot be null");
        }
    }

    @Test
    public void testCheckReferencesIgnoresDoiDigitsWhenExtractingYear() {
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[1]")
                        .setRawText("张三, 李四. 论文题名[J]. 期刊名, 2017, 35(6):18-21,25. DOI:10.3969/j.issn.1001-2257.2017.06.004.")
                        .setIsValidFormat(true)
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[2]")
                        .setRawText("张三, 李四. 书名[M]. 北京: 出版社, 2020. DOI:10.1234/abcd.2020.01.")
                        .setIsValidFormat(true)
                        .build())
                .build();

        List<Issue> issues = referenceChecker.checkReferences(data);

        assertNotNull(issues);
        assertFalse(issues.stream().anyMatch(issue ->
                "ERR_REF_JOURNAL_YEAR_EXCEED".equals(issue.getCode())
                        || "ERR_REF_JOURNAL_YEAR_EARLY".equals(issue.getCode())
                        || "ERR_REF_MONO_YEAR_EXCEED".equals(issue.getCode())
                        || "ERR_REF_MONO_YEAR_EARLY".equals(issue.getCode())
                        || "ERR_REF_JOURNAL_YEAR_TWO_DIGIT".equals(issue.getCode())
                        || "ERR_REF_MONO_YEAR_TWO_DIGIT".equals(issue.getCode())),
                "DOI digits should not be treated as publication years");
    }

    private ParsedData createValidParsedDataWithReferences() {
        return ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(10)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("paragraph")
                        .setLevel(0)
                        .setText("根据研究[1]表明...")
                        .build())
                .addReferences(Reference.newBuilder()
                        .setRefId("[1]")
                        .setRawText("张三, 李四. 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                        .setIsValidFormat(true)
                        .build())
                .build();
    }
}