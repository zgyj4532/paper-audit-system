package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * GB/T 7714 Large Scale Stress Test - Simulate 20 Types of Real Errors
 * Automatically generate 200 random reference entries and 200 formatting paragraphs
 */
public class GB7714LargeScaleTest {
    
    private static final Logger logger = LoggerFactory.getLogger(GB7714LargeScaleTest.class);
    private final ReferenceChecker referenceChecker = new ReferenceChecker();
    private final FormattingAuditor formattingAuditor = new FormattingAuditor();
    
    // Random material pool
    private final String[] AUTHORS = {"张三", "李四", "王五", "赵六", "钱七", "Sun W.", "James A.", "Liu Y.", "Chen H."};
    private final String[] TITLES = {"深度学习研究", "区块链审计系统", "大语言模型综述", "分布式系统设计", "规则引擎实战"};
    private final String[] JOURNALS = {"计算机学报", "软件学报", "IEEE Transactions", "Nature", "Science"};
    private final String[] PUBLISHERS = {"科学出版社", "清华大学出版社", "Springer", "Elsevier"};

    @Test
    public void testGB7714With200References() throws Exception {
        // 1. Generate 200 random test data entries
        ParsedData data = generateLargeScaleTestData();
        
        // 2. Perform audit
        List<Issue> issues = referenceChecker.checkReferences(data);
        
        // 3. Count results and print
        printSummary("GB/T 7714 Reference Large Scale Audit", 200, issues);
        
        // 4. Print first 40 detail samples
        System.out.println("\n>>> [Audit Evidence Sample] Reference Details (First 40):");
        System.out.printf("%-6s | %-30s | %-25s | %s\n", "Index", "Error Code", "Text Snippet", "Suggestion");
        System.out.println("---------------------------------------------------------------------------------------");
        
        issues.stream().limit(40).forEach(issue -> {
            String snippet = issue.getOriginalSnippet().length() > 20 
                ? issue.getOriginalSnippet().substring(0, 20).replace("\n", "") + "..." 
                : issue.getOriginalSnippet().replace("\n", "");
            
            System.out.printf("Ref    | %-30s | %-25s | %s\n", 
                issue.getCode(), 
                snippet, 
                issue.getSuggestion());
        });

        // 5. Persist to file
        saveIssuesToFile(issues, "target/reference_audit_detail.txt");
        assertTrue(issues.size() >= 200, "200 test entries should detect at least 200 issues");
    }

    @Test
    public void testFormattingWith200Sections() throws Exception {
        ParsedData data = generateFormattingTestData();
        List<Issue> issues = formattingAuditor.checkFormatting(data);
        
        printSummary("Formatting Rules Large Scale Audit", 200, issues);
        saveIssuesToFile(issues, "target/formatting_audit_detail.txt");
        assertTrue(issues.size() > 0);
    }

    private ParsedData generateLargeScaleTestData() {
        ParsedData.Builder builder = ParsedData.newBuilder().setDocId("REF-VOL-2026");
        
        // Generate 200 entries, loop 10 times over 20 error types
        for (int i = 1; i <= 200; i++) {
            int type = (i - 1) % 20; 
            String author = AUTHORS[i % AUTHORS.length];
            String title = TITLES[i % TITLES.length];
            String journal = JOURNALS[i % JOURNALS.length];
            String pub = PUBLISHERS[i % PUBLISHERS.length];
            int year = 2010 + (i % 15); 

            String rawText;
            switch (type) {
                case 0: rawText = String.format("[%d] %s，%s. %s[J]. %s, %d.", i, author, "李四", title, journal, year); break;
                case 1: rawText = String.format("[%d] %s, %s. %s[J]. %s, %d.", i, author, "李四", title, journal, 2027 + i % 10); break;
                case 2: rawText = String.format("[%d] %s, %s. %s[J] %s, %d.", i, author, "李四", title, journal, year); break;
                case 3: rawText = String.format("[%d] %s, %s. %s[J]. %s, %d, 1-10.", i, author, "李四", title, journal, year); break;
                case 4: rawText = String.format("[%d] %s, %s. %s[J]. %s, %d, 10(2).", i, author, "李投", title, journal, year); break;
                case 5: rawText = String.format("[%d] %s, 李四, 王五, 赵六. %s[J]. %s, %d.", i, author, title, journal, year); break;
                case 6: rawText = String.format("[%d] %s。 %s[M]。 北京: %s, %d.", i, author, title, pub, year); break;
                case 7: rawText = String.format("[%d] %s. %s[M]. 北京: %s, %d.", i, author, title, pub, 2030 + (i % 5)); break;
                case 8: rawText = String.format("[%d] %s. %s[M] 北京: %s, %d.", i, author, title, pub, year); break;
                case 9: rawText = String.format("[%d] %s. %s[M]. %d.", i, author, title, year); break;
                case 10: rawText = String.format("[%d] %s, %s. %s[J]；%s, %d.", i, author, "李四", title, journal, year); break;
                case 11: rawText = String.format("[%d] %s, 李四, 王五, 赵六. %s[M]. 北京: %s, %d.", i, author, title, pub, year); break;
                case 12: rawText = String.format("[%d] %s, %s. %s[J]. %s, %d.", i, author, "李四", title, journal, i % 99); break;
                case 13: rawText = String.format("[%d] %s, %s. %s[J]. %s, 1850.", i, author, "李四", title, journal); break;
                case 14: rawText = String.format("[%d] %s. %s[M]. 北京: %s, 95.", i, author, title, pub); break;
                case 15: rawText = String.format("[%d] %s, %s。%s[J]. %s, %d.", i, author, "李四", title, journal, year); break;
                case 16: rawText = String.format("[%d] %s。 %s[M]. 北京: %s, %d.", i, author, title, pub, year); break;
                case 17: rawText = String.format("[%d] %s[J]. %s, %d.", i, title, journal, year); break;
                case 18: rawText = String.format("[%d] %s[M]. 北京: %s, %d.", i, title, pub, year); break;
                case 19: 
                default: rawText = String.format("[%d] %s, %s. %s[j]. %s, %d.", i, author, "李四", title, journal, year); break;
            }
            
            builder.addReferences(Reference.newBuilder()
                    .setRefId("[" + i + "]")
                    .setRawText(rawText)
                    .build());
        }
        return builder.build();
    }

    private ParsedData generateFormattingTestData() {
        ParsedData.Builder builder = ParsedData.newBuilder().setDocId("F-200");
        // Generate 200 sections, each type loops over 5 format errors
        // Rule engine uses getPropsMap().get(key) to read props, key is hyphenated format
        for (int i = 1; i <= 200; i++) {
            int errorType = (i - 1) % 5;
            Section.Builder sb = Section.newBuilder()
                    .setSectionId(i)
                    .setText("Test formatting paragraph " + i);
            switch (errorType) {
                case 0:
                    // Line spacing does not meet standard (should be 1.5, given 2.0 triggers FMT_LINE_HEIGHT_001)
                    sb.setType("paragraph")
                      .putProps("line-height", "2.0")
                      .putProps("font-family", "SimSun")
                      .putProps("font-size", "12");
                    break;
                case 1:
                    // Body font error (should be SimSun, given Arial triggers font rule)
                    sb.setType("paragraph")
                      .putProps("line-height", "1.5")
                      .putProps("font-family", "Arial")
                      .putProps("font-size", "12");
                    break;
                case 2:
                    // Body font size error (should be 12, given 14 triggers size rule)
                    sb.setType("paragraph")
                      .putProps("line-height", "1.5")
                      .putProps("font-family", "SimSun")
                      .putProps("font-size", "14");
                    break;
                case 3:
                    // Alignment error (should be LEFT, given CENTER triggers alignment rule)
                    sb.setType("paragraph")
                      .putProps("line-height", "1.5")
                      .putProps("font-family", "SimSun")
                      .putProps("font-size", "12")
                      .putProps("alignment", "CENTER");
                    break;
                case 4:
                    // Heading font error (should be SimHei, given Arial)
                    sb.setType("heading")
                      .setLevel(1)
                      .putProps("line-height", "1.5")
                      .putProps("font-family", "Arial")
                      .putProps("font-size", "15");
                    break;
                default:
                    sb.setType("paragraph")
                      .putProps("line-height", "2.0")
                      .putProps("font-family", "Arial")
                      .putProps("font-size", "14");
            }
            builder.addSections(sb.build());
        }
        return builder.build();
    }

    private void saveIssuesToFile(List<Issue> issues, String filePath) throws Exception {
        try (PrintWriter writer = new PrintWriter(filePath, StandardCharsets.UTF_8)) {
            writer.println("Audit Module Detailed Report - " + new Date());
            writer.println("==================================================");
            for (Issue issue : issues) {
                writer.printf("ID: %d | Code: %s | Suggestion: %s | Text: %s\n", 
                    issue.getSectionId(), issue.getCode(), issue.getSuggestion(), issue.getOriginalSnippet().replace("\n", " "));
            }
        }
    }

    private void printSummary(String title, int total, List<Issue> issues) {
        Map<String, Integer> stats = new TreeMap<>();
        issues.forEach(i -> stats.put(i.getCode(), stats.getOrDefault(i.getCode(), 0) + 1));
        System.out.println("\n========== " + title + " ==========");
        System.out.println("Total Samples: " + total + " | Total Detected: " + issues.size());
        stats.forEach((code, count) -> System.out.println("  - " + code + ": " + count + " entries"));
    }
}