package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import static org.junit.jupiter.api.Assertions.assertTrue;

public class FormattingCoverageTest {

    private static final Logger logger = LoggerFactory.getLogger(FormattingCoverageTest.class);
    private FormattingAuditor formattingAuditor;

    @BeforeEach
    public void setUp() {
        formattingAuditor = new FormattingAuditor();
    }

    @Test
    public void testFormattingAccuracy200() throws IOException {
        // 1. Generate test data
        ParsedData data = generate200FormattingTestData();
        
        // 2. Execute audit check
        List<Issue> issues = formattingAuditor.checkFormatting(data);

        // 3. Output each specific record
        System.out.println("\n>>>>>> Audit module detailed output start <<<<<<");
        for (Issue issue : issues) {
            System.out.printf("ID: %-4d | Code: %-25s | Suggestion: %s%n", 
                issue.getSectionId(), 
                issue.getCode(), 
                issue.getMessage());
        }
        System.out.println(">>>>>> Audit module detailed output end <<<<<<\n");

        // 4. Statistics of each rule detection
        Map<String, Integer> detectionStats = new TreeMap<>();
        for (Issue issue : issues) {
            detectionStats.put(issue.getCode(), detectionStats.getOrDefault(issue.getCode(), 0) + 1);
        }

        logger.info("=== Formatting Rules Accuracy Test Statistics ===");
        logger.info("Total test samples: 200");
        logger.info("Total detected issues: {}", issues.size());
        
        detectionStats.forEach((code, count) -> {
            logger.info("Rule [{}] detection count: {}", code, count);
        });

        // 5. Save detailed report to file
        saveDetailReport(issues, detectionStats);

        // 6. Assert: All 200 data have formatting issues, detection count should be >= 190
        assertTrue(issues.size() >= 190, "Formatting rule detection rate too low, current detection count: " + issues.size());
    }

    /**
     * Save 200 details to a txt file under target directory
     */
    private void saveDetailReport(List<Issue> issues, Map<String, Integer> stats) throws IOException {
        File reportFile = new File("target/formatting_audit_detail.txt");
        try (PrintWriter writer = new PrintWriter(new FileWriter(reportFile))) {
            writer.println("Audit module detailed report - " + LocalDateTime.now());
            writer.println("==================================================");
            
            for (Issue issue : issues) {
                writer.printf("ID: %-5d | Code: %-25s | Suggestion: %s%n", 
                    issue.getSectionId(), issue.getCode(), issue.getMessage());
            }

            writer.println("\n================ Statistics Summary ================");
            stats.forEach((code, count) -> writer.printf("%-25s : %d items%n", code, count));
            writer.println("Total detected: " + issues.size() + " records");
        }
        logger.info(">>> Detailed report generated at: {}", reportFile.getAbsolutePath());
    }

    private ParsedData generate200FormattingTestData() {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId("TEST_FMT_200");

        int sectionIdCounter = 1;

        // ── formatting.drl rule correspondence ──────────────────────────────────────────
        // Rule 1  FMT_LINE_HEIGHT_001  : paragraph/heading, line-height not within 1.5±0.05
        // Rule 5  FMT_HEADING_FONT_001 : heading level=1, font-family does not contain "黑体"
        // Rule 6  FMT_HEADING_SIZE_001 : heading level=1, font-size not within 18±1
        // Rule 7  FMT_HEADING_FONT_002 : heading level=2, font-family does not contain "黑体"
        // Rule 8  FMT_HEADING_SIZE_002 : heading level=2, font-size not within 16±1
        // Rule 11 FMT_BODY_FONT_001    : paragraph, font-family does not contain "宋体"/"仿宋"
        // Rule 12 FMT_BODY_SIZE_001    : paragraph, font-size not within 12±1
        // Rule 4  FMT_FORMULA_ALIGNMENT: formula, alignment != "right"
        // Rule 3  FMT_TABLE_PAGE_BREAK : table, page-break=true and continue-table-flag=false
        // Rule 2  FMT_HEADING_LEVEL_JUMP: consecutive two headings level jump (e.g. 1→3)
        // ─────────────────────────────────────────────────────────────────────────

        // 1. Line height check (FMT_LINE_HEIGHT_001) - 20 items
        //    paragraph + line-height=2.0 (not within 1.5±0.05) → triggers line height rule
        //    font-family="Arial" (does not contain "宋体"/"仿宋") → also triggers FMT_BODY_FONT_001
        for (int i = 0; i < 20; i++) {
            double invalidLineHeight = 2.0 + (i * 0.1);
            builder.addSections(createSection(sectionIdCounter++, "paragraph", 0, "Line height error sample",
                Map.of("line-height", String.valueOf(invalidLineHeight),
                       "font-family", "Arial",
                       "font-size",   "12")));
        }

        // 2. Level 1 heading font (FMT_HEADING_FONT_001) - 20 items
        //    heading level=1, font-family="Arial" (does not contain "黑体") → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "heading", 1, "Level 1 heading font error",
                Map.of("font-family", "Arial",
                       "font-size",   "18")));
        }

        // 3. Level 1 heading font size (FMT_HEADING_SIZE_001) - 20 items
        //    heading level=1, font-family="黑体" (passes font check), font-size=14 (not within 18±1) → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "heading", 1, "Level 1 heading font size error",
                Map.of("font-family", "黑体",
                       "font-size",   "14")));
        }

        // 4. Level 2 heading font (FMT_HEADING_FONT_002) - 20 items
        //    heading level=2, font-family="Arial" (does not contain "黑体") → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "heading", 2, "Level 2 heading font error",
                Map.of("font-family", "Arial",
                       "font-size",   "16")));
        }

        // 5. Level 2 heading font size (FMT_HEADING_SIZE_002) - 20 items
        //    heading level=2, font-family="黑体" (passes font check), font-size=12 (not within 16±1) → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "heading", 2, "Level 2 heading font size error",
                Map.of("font-family", "黑体",
                       "font-size",   "12")));
        }

        // 6. Body font check (FMT_BODY_FONT_001) - 20 items
        //    paragraph, font-family="Microsoft YaHei" (does not contain "宋体"/"仿宋") → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "paragraph", 0, "Body font error",
                Map.of("font-family", "Microsoft YaHei",
                       "font-size",   "12")));
        }

        // 7. Body font size check (FMT_BODY_SIZE_001) - 20 items
        //    paragraph, font-family="宋体" (passes font check), font-size=10 (not within 12±1) → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "paragraph", 0, "Body font size error",
                Map.of("font-family", "宋体",
                       "font-size",   "10")));
        }

        // 8. Formula alignment check (FMT_FORMULA_ALIGNMENT) - 20 items
        //    formula, alignment="left" (not equal to "right") → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "formula", 0, "E=mc^2",
                Map.of("alignment", "left")));
        }

        // 9. Table page break continuation flag (FMT_TABLE_PAGE_BREAK) - 20 items
        //    table, page-break=true and continue-table-flag=false → triggers
        for (int i = 0; i < 20; i++) {
            builder.addSections(createSection(sectionIdCounter++, "table", 0, "Data table",
                Map.of("page-break", "true", "continue-table-flag", "false")));
        }

        // 10. Heading level jump (FMT_HEADING_LEVEL_JUMP) - 20 items
        //     heading(level=1) immediately followed by heading(level=3), jump more than 1 level → triggers
        for (int i = 0; i < 10; i++) {
            builder.addSections(createSection(sectionIdCounter++, "heading", 1, "Chapter title", Map.of()));
            builder.addSections(createSection(sectionIdCounter++, "heading", 3, "Skipped level heading", Map.of()));
        }

        return builder.build();
    }

    private Section createSection(int id, String type, int level, String text, Map<String, String> props) {
        return Section.newBuilder()
                .setSectionId(id)
                .setType(type)
                .setLevel(level)
                .setText(text)
                .putAllProps(props)
                .build();
    }
}