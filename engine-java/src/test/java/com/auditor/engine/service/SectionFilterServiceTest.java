package com.auditor.engine.service;

import com.auditor.grpc.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * SectionFilterService Special Test
 *
 * <p>Important design constraint: stop detection only applies to sections with <b>type=heading</b>,
 * directory entries with type=paragraph (e.g., "学位论文数据集\t25") do not trigger truncation.
 *
 * <p>Test coverage:
 * <ol>
 *   <li>Unit tests: stop keyword truncation (triggered by heading / not triggered by paragraph), whitelist skip, null/empty input safety handling</li>
 *   <li>Integration tests: verify filtering effect based on real JSON file (Li Liangxun's thesis)</li>
 *   <li>End-to-end tests: filtered data sent to IntegrityScanner / FormattingAuditor,
 *       verify no false positives in "学位论文数据集" section</li>
 * </ol>
 */
public class SectionFilterServiceTest {

    private static final Logger logger = LoggerFactory.getLogger(SectionFilterServiceTest.class);

    private SectionFilterService filterService;
    private ObjectMapper objectMapper;

    @BeforeEach
    public void setUp() {
        filterService = new SectionFilterService();
        objectMapper = new ObjectMapper();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 1. Unit tests: matchesStopKeyword
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("Stop keyword: containing '学位论文数据集' should hit")
    public void testMatchesStopKeyword_hit() {
        assertTrue(filterService.matchesStopKeyword("学位论文数据集"));
        assertTrue(filterService.matchesStopKeyword("学位论文数据集\t25"));   // with tab + page number
        assertTrue(filterService.matchesStopKeyword("  学位论文数据集  "));   // with spaces
    }

    @Test
    @DisplayName("Stop keyword: normal text should not hit")
    public void testMatchesStopKeyword_miss() {
        assertFalse(filterService.matchesStopKeyword("摘要"));
        assertFalse(filterService.matchesStopKeyword("参考文献"));
        assertFalse(filterService.matchesStopKeyword("结论"));
        assertFalse(filterService.matchesStopKeyword(null));
        assertFalse(filterService.matchesStopKeyword(""));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 2. Unit tests: isWhitelisted
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("Whitelist: exact match should hit")
    public void testIsWhitelisted_hit() {
        assertTrue(filterService.isWhitelisted("学位论文数据集"));
        assertTrue(filterService.isWhitelisted("独创性声明"));
        assertTrue(filterService.isWhitelisted("学位论文版权使用授权书"));
        assertTrue(filterService.isWhitelisted("版权声明"));
    }

    @Test
    @DisplayName("Whitelist: non-whitelist text should not hit")
    public void testIsWhitelisted_miss() {
        assertFalse(filterService.isWhitelisted("学位论文数据集\t25"));  // with tab not exact match
        assertFalse(filterService.isWhitelisted("摘要"));
        assertFalse(filterService.isWhitelisted(null));
        assertFalse(filterService.isWhitelisted(""));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 3. Unit tests: filterSections truncation logic
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("filterSections: null input safely returns null")
    public void testFilterSections_null() {
        assertNull(filterService.filterSections(null));
    }

    @Test
    @DisplayName("filterSections: keep all when no keyword")
    public void testFilterSections_noKeyword() {
        // All paragraph, no keyword → keep all
        ParsedData data = buildParsedData("摘要", "第一章 绪论", "第二章 方法", "结论", "参考文献");
        ParsedData result = filterService.filterSections(data);
        assertEquals(5, result.getSectionsCount(), "All sections should be kept when no keyword");
    }

    @Test
    @DisplayName("filterSections: paragraph type directory entries do not trigger truncation")
    public void testFilterSections_paragraphNotTrigger() {
        // Directory entries are paragraph type, even if containing keyword do not truncate
        ParsedData data = buildParsedData("摘要", "第一章", "结论", "参考文献", "学位论文数据集\t25");
        // buildParsedData defaults to type=paragraph, so "学位论文数据集\t25" does not trigger truncation
        ParsedData result = filterService.filterSections(data);
        assertEquals(5, result.getSectionsCount(), "Paragraph type directory entries should not trigger truncation, all 5 should be kept");
    }

    @Test
    @DisplayName("filterSections: heading type keyword at end, truncate last 1")
    public void testFilterSections_headingStopAtEnd() {
        // Last one is heading type "学位论文数据集" → triggers truncation
        ParsedData data = buildParsedDataMixed(
            new SectionSpec("摘要",       "paragraph"),
            new SectionSpec("第一章",     "paragraph"),
            new SectionSpec("结论",       "paragraph"),
            new SectionSpec("参考文献",   "paragraph"),
            new SectionSpec("学位论文数据集", "heading")   // ← heading, triggers truncation
        );
        ParsedData result = filterService.filterSections(data);
        assertEquals(4, result.getSectionsCount(), "Heading keyword at end should truncate 1");
        assertEquals("参考文献", result.getSections(3).getText());
    }

    @Test
    @DisplayName("filterSections: heading type keyword in middle, truncate all following")
    public void testFilterSections_headingStopInMiddle() {
        ParsedData data = buildParsedDataMixed(
            new SectionSpec("摘要",           "paragraph"),
            new SectionSpec("第一章",         "paragraph"),
            new SectionSpec("学位论文数据集", "heading"),   // ← heading, triggers truncation
            new SectionSpec("附录A",          "paragraph"),
            new SectionSpec("附录B",          "paragraph")
        );
        ParsedData result = filterService.filterSections(data);
        assertEquals(2, result.getSectionsCount(), "Heading keyword in middle should truncate following 3");
    }

    @Test
    @DisplayName("filterSections: heading type keyword at beginning, result empty")
    public void testFilterSections_headingStopAtBeginning() {
        ParsedData data = buildParsedDataMixed(
            new SectionSpec("学位论文数据集", "heading"),   // ← heading, triggers truncation
            new SectionSpec("摘要",           "paragraph"),
            new SectionSpec("结论",           "paragraph")
        );
        ParsedData result = filterService.filterSections(data);
        assertEquals(0, result.getSectionsCount(), "Heading keyword at beginning should result in empty");
    }

    @Test
    @DisplayName("filterSections: whitelist sections are silently skipped")
    public void testFilterSections_whitelistSkipped() {
        ParsedData data = buildParsedData("摘要", "独创性声明", "第一章", "版权声明", "结论");
        ParsedData result = filterService.filterSections(data);
        // 独创性声明 and 版权声明 are skipped, remaining 摘要、第一章、结论
        assertEquals(3, result.getSectionsCount(), "Whitelist sections should be skipped");
        assertEquals("摘要", result.getSections(0).getText());
        assertEquals("第一章", result.getSections(1).getText());
        assertEquals("结论", result.getSections(2).getText());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 4. Integration tests: based on real JSON file
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("Real document: Li Liangxun thesis JSON - filtered result does not contain '学位论文数据集' title line and its table content")
    public void testRealDocument_jsonFilter() throws Exception {
        ParsedData rawData = loadRealDocumentJson();
        if (rawData == null) {
            logger.warn("Skip real document test: JSON file does not exist");
            return;
        }

        int originalCount = rawData.getSectionsCount();
        logger.info("Original section count: {}", originalCount);

        // Verify JSON contains table rows (type=table_row)
        long tableRowCount = rawData.getSectionsList().stream()
                .filter(s -> "table_row".equals(s.getType()))
                .count();
        logger.info("JSON contains {} table_row type sections", tableRowCount);
        assertTrue(tableRowCount > 0, "JSON should contain thesis dataset table rows (table_row), actual count=" + tableRowCount);

        // Verify section_id=64 in JSON is paragraph type directory entry (should not trigger truncation)
        boolean hasParagraphToc = rawData.getSectionsList().stream()
                .anyMatch(s -> s.getSectionId() == 64
                        && "paragraph".equals(s.getType())
                        && s.getText().contains("学位论文数据集"));
        assertTrue(hasParagraphToc, "section_id=64 should be paragraph type directory entry");

        // Verify last section in JSON is heading type "学位论文数据集" (should trigger truncation)
        boolean hasHeadingStop = rawData.getSectionsList().stream()
                .anyMatch(s -> "heading".equals(s.getType())
                        && s.getText().contains("学位论文数据集"));
        assertTrue(hasHeadingStop, "JSON should contain heading type '学位论文数据集' section title");

        ParsedData filtered = filterService.filterSections(rawData);
        int filteredCount = filtered.getSectionsCount();
        logger.info("Filtered section count: {}", filteredCount);

        // Verify: filtered count less than original (truncated heading title line + 21 table rows = 22)
        assertTrue(filteredCount < originalCount,
                "Filtered section count should be less than original, original=" + originalCount + " filtered=" + filteredCount);

        // Verify: truncation count is 22 (1 heading title + 21 table_row)
        int removedCount = originalCount - filteredCount;
        assertEquals(22, removedCount,
                "Should truncate 22 sections (1 heading title line + 21 table_row), actual truncated=" + removedCount);

        // Verify: no heading type "学位论文数据集" after filtering
        boolean hasStopHeading = filtered.getSectionsList().stream()
                .anyMatch(s -> "heading".equals(s.getType())
                        && filterService.matchesStopKeyword(s.getText()));
        assertFalse(hasStopHeading, "No heading type '学位论文数据集' should exist after filtering");

        // Verify: no table_row after filtering (all table rows truncated)
        long filteredTableRows = filtered.getSectionsList().stream()
                .filter(s -> "table_row".equals(s.getType()))
                .count();
        assertEquals(0, filteredTableRows,
                "No table_row should exist after filtering, thesis dataset tables should be fully truncated, actual count=" + filteredTableRows);

        // Verify: paragraph type directory entry "学位论文数据集\t25" still kept (not truncated)
        boolean hasTocEntry = filtered.getSectionsList().stream()
                .anyMatch(s -> "paragraph".equals(s.getType())
                        && s.getText().contains("学位论文数据集"));
        assertTrue(hasTocEntry, "Paragraph type directory entry '学位论文数据集\\t25' should be kept in filtered result");

        logger.info("Truncation summary: original {} sections, truncated {} (1 heading title line + {} table_row)",
                originalCount, removedCount, tableRowCount);
    }

    @Test
    @DisplayName("Real document: filtered data sent to IntegrityScanner, no false positives related to '学位论文数据集'")
    public void testRealDocument_integrityNoFalsePositive() throws Exception {
        ParsedData rawData = loadRealDocumentJson();
        if (rawData == null) {
            logger.warn("Skip real document test: JSON file does not exist");
            return;
        }

        IntegrityScanner scanner = new IntegrityScanner();
        List<Issue> issues = scanner.checkIntegrity(rawData);

        logger.info("Integrity check found {} issues", issues.size());

        // Verify: no issue's originalSnippet contains '学位论文数据集'
        boolean hasFalsePositive = issues.stream()
                .anyMatch(i -> i.getOriginalSnippet().contains("学位论文数据集")
                        || i.getMessage().contains("学位论文数据集"));
        assertFalse(hasFalsePositive, "Integrity check should not produce issues for '学位论文数据集' section");

        for (Issue issue : issues) {
            logger.info("  Issue: [{}] {} @ section {}",
                    issue.getSeverity(), issue.getMessage(), issue.getSectionId());
        }
    }

    @Test
    @DisplayName("Real document: filtered data sent to FormattingAuditor, no false positives related to '学位论文数据集'")
    public void testRealDocument_formattingNoFalsePositive() throws Exception {
        ParsedData rawData = loadRealDocumentJson();
        if (rawData == null) {
            logger.warn("Skip real document test: JSON file does not exist");
            return;
        }

        FormattingAuditor auditor = new FormattingAuditor();
        List<Issue> issues = auditor.checkFormatting(rawData);

        logger.info("Formatting check found {} issues", issues.size());

        boolean hasFalsePositive = issues.stream()
                .anyMatch(i -> i.getOriginalSnippet().contains("学位论文数据集")
                        || i.getMessage().contains("学位论文数据集"));
        assertFalse(hasFalsePositive, "Formatting check should not produce issues for '学位论文数据集' section");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helper methods
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Load real test JSON from classpath or file system, convert to ParsedData.
     * Returns null if file does not exist (test will be skipped).
     */
    private ParsedData loadRealDocumentJson() throws Exception {
        java.net.URL resourceUrl = getClass().getClassLoader()
                .getResource("data/audit_results_final.json");
        File jsonFile;
        if (resourceUrl != null) {
            jsonFile = new File(resourceUrl.getFile());
        } else {
            jsonFile = new File("src/test/resources/data/audit_results_final.json");
        }

        if (!jsonFile.exists()) {
            logger.warn("JSON file does not exist: {}", jsonFile.getAbsolutePath());
            return null;
        }

        logger.info("Loading real document JSON: {}", jsonFile.getAbsolutePath());
        JsonNode root = objectMapper.readTree(jsonFile);
        return convertJsonToParsedData(root);
    }

    /**
     * Convert JSON node to ParsedData (consistent with RealDocumentAuditTest).
     */
    private ParsedData convertJsonToParsedData(JsonNode rootNode) {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId(rootNode.path("doc_id").asText("unknown"));

        JsonNode meta = rootNode.get("metadata");
        if (meta != null) {
            builder.setMetadata(DocumentMetadata.newBuilder()
                    .setTitle(meta.path("title").asText(""))
                    .setPageCount(meta.path("total_pages").asInt(0))
                    .build());
        }

        JsonNode sections = rootNode.get("sections");
        if (sections != null && sections.isArray()) {
            for (JsonNode sn : sections) {
                Section.Builder sb = Section.newBuilder()
                        .setSectionId(sn.path("section_id").asInt())
                        .setType(sn.path("type").asText("paragraph"))
                        .setLevel(sn.path("level").asInt(0))
                        .setText(sn.path("text").asText(""));
                JsonNode props = sn.get("properties");
                if (props != null) {
                    props.fields().forEachRemaining(e ->
                            sb.putProps(e.getKey(), e.getValue().asText()));
                }
                builder.addSections(sb.build());
            }
        }

        if (rootNode.has("references")) {
            for (JsonNode rn : rootNode.get("references")) {
                builder.addReferences(Reference.newBuilder()
                        .setRefId(rn.path("ref_id").asText(""))
                        .setRawText(rn.path("raw_text").asText(""))
                        .build());
            }
        }

        return builder.build();
    }

    /**
     * Build a ParsedData containing specified text list, all sections are type=paragraph.
     * Used for testing whitelist and other scenarios not depending on type.
     */
    private ParsedData buildParsedData(String... texts) {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(texts.length)
                        .build());
        for (int i = 0; i < texts.length; i++) {
            builder.addSections(Section.newBuilder()
                    .setSectionId(i + 1)
                    .setType("paragraph")   // all paragraph, no stop detection triggered
                    .setLevel(0)
                    .setText(texts[i])
                    .build());
        }
        return builder.build();
    }

    /**
     * Build a ParsedData containing specified SectionSpec list, supports custom type.
     * Used for testing heading type triggering truncation scenarios.
     */
    private ParsedData buildParsedDataMixed(SectionSpec... specs) {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId("test-doc")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("Test Document")
                        .setPageCount(specs.length)
                        .build());
        for (int i = 0; i < specs.length; i++) {
            builder.addSections(Section.newBuilder()
                    .setSectionId(i + 1)
                    .setType(specs[i].type)
                    .setLevel("heading".equals(specs[i].type) ? 1 : 0)
                    .setText(specs[i].text)
                    .build());
        }
        return builder.build();
    }

    /** Helper data class: section text + type */
    private static class SectionSpec {
        final String text;
        final String type;
        SectionSpec(String text, String type) {
            this.text = text;
            this.type = type;
        }
    }
}