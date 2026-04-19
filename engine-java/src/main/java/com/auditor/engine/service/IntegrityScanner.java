package com.auditor.engine.service;

import com.auditor.grpc.*;
import com.auditor.engine.mock.MockDroolsEngine;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;

import java.util.ArrayList;
import java.util.List;

@Service
public class IntegrityScanner {

    /** section pre-filtering service (stop detection + whitelist) */
    private final SectionFilterService sectionFilterService = new SectionFilterService();

    private static final Logger logger = LoggerFactory.getLogger(IntegrityScanner.class);
    private KieContainer kieContainer;

    public IntegrityScanner() {
        try {
            KieServices kieServices = KieServices.Factory.get();
            kieContainer = kieServices.getKieClasspathContainer();
            logger.info("Integrity check rule engine initialized successfully");
        } catch (Exception e) {
            logger.warn("Drools rule engine initialization failed, using mock engine: {}", e.getMessage());
            kieContainer = null;
        }
    }

    public List<Issue> scanIntegrity(ParsedData rawData) {
        List<Issue> issues = new ArrayList<>();

        if (rawData == null || !rawData.hasMetadata()) {
            logger.warn("Input data is null or missing metadata");
            issues.add(createErrorIssue("ERR_INTEGRITY_NULL",
                    "无法识别文档类型：输入数据为空或缺少元数据", 0, Severity.CRITICAL));
            return issues;
        }

        // ── Pre-filtering: truncate "Thesis dataset" and subsequent sections ──
        ParsedData data = sectionFilterService.filterSections(rawData);
        logger.info("Integrity check section pre-filtering: original {} → filtered {}",
                rawData.getSectionsCount(), data.getSectionsCount());

        logger.info("Starting integrity check, Document ID: {}, Title: {}",
                data.getDocId(), data.getMetadata().getTitle());

        // Use Drools if available; otherwise use mock engine
        if (kieContainer != null) {
            return scanIntegrityWithDrools(data, issues);
        } else {
            logger.info("Using mock Drools engine for integrity check");
            return MockDroolsEngine.checkIntegrityRules(data);
        }
    }

    private List<Issue> scanIntegrityWithDrools(ParsedData data, List<Issue> issues) {
        KieSession kieSession = null;

        try {
            kieSession = kieContainer.newKieSession("integritySession");

            kieSession.setGlobal("results", issues);
            kieSession.setGlobal("logger", logger);

            kieSession.insert(data);
            for (Section section : data.getSectionsList()) {
                kieSession.insert(section);
            }

            int firedRules = kieSession.fireAllRules();
            logger.info("Integrity check completed, fired {} rules, found {} issues",
                    firedRules, issues.size());

        } catch (Exception e) {
            logger.error("Integrity check execution exception", e);
            issues.add(createErrorIssue("ERR_INTEGRITY_ENGINE",
                    "Integrity check engine exception: " + e.getMessage(), 0, Severity.HIGH));
        } finally {
            if (kieSession != null) {
                kieSession.dispose();
            }
        }

        return issues;
    }

    /**
     * Check section integrity
     */
    public List<Issue> checkIntegrity(ParsedData rawData) {
        List<Issue> issues = new ArrayList<>();

        if (rawData == null || rawData.getSectionsCount() == 0) {
            logger.warn("Input data is null or has no sections");
            return issues;
        }

        // ── Pre-filtering ──
        ParsedData data = sectionFilterService.filterSections(rawData);
        logger.info("Section integrity check pre-filtering: original {} → filtered {}",
                rawData.getSectionsCount(), data.getSectionsCount());

        try {
            checkSectionNumbering(data, issues);
            checkHeadingHierarchy(data, issues);
            checkRequiredSections(data, issues);
            checkFigureTableNumbering(data, issues);
            checkDocumentStructure(data, issues);

        } catch (Exception e) {
            logger.error("Section integrity check exception", e);
            issues.add(createErrorIssue("ERR_INTEGRITY_CHECK",
                    "Section integrity check exception: " + e.getMessage(), 0, Severity.HIGH));
        }

        logger.info("Section integrity check completed, found {} issues", issues.size());
        return issues;
    }

    private void checkSectionNumbering(ParsedData data, List<Issue> issues) {
        // section_id is an internal ID assigned by Rust parser, allowing skipped numbers (e.g., TOC occupies some IDs),
        // only requires section_id to be monotonically increasing (no disorder or duplicates), not strictly continuous.
        int lastSectionId = -1;
        for (Section section : data.getSectionsList()) {
            int currentId = section.getSectionId();
            if (currentId <= lastSectionId) {
                Issue issue = createIntegrityIssue("ERR_INT_NUM_001",
                        "Section ID disorder or duplicate: previous ID was " + lastSectionId + ", current ID is " + currentId,
                        currentId,
                        "Check document parsing results to ensure correct section order",
                        section.getText());
                issues.add(issue);
            }
            lastSectionId = currentId;
        }
    }

    private void checkHeadingHierarchy(ParsedData data, List<Issue> issues) {
        int lastLevel = 0;
        int lastSectionId = 0;

        for (Section section : data.getSectionsList()) {
            if ("heading".equals(section.getType())) {
                int currentLevel = section.getLevel();

                if (currentLevel > lastLevel + 1) {
                    Issue issue = createIntegrityIssue("ERR_INT_HIER_001",
                            "Heading level jump: from level " + lastLevel + " to level " + currentLevel,
                            section.getSectionId(),
                            "Heading levels should increase stepwise",
                            section.getText());
                    issues.add(issue);
                }

                if (currentLevel == lastLevel && section.getSectionId() <= lastSectionId) {
                    Issue issue = createIntegrityIssue("ERR_INT_HIER_002",
                            "Same-level heading order error: heading order is confused",
                            section.getSectionId(),
                            "Adjust the order of same-level headings",
                            section.getText());
                    issues.add(issue);
                }

                lastLevel = currentLevel;
                lastSectionId = section.getSectionId();
            }
        }
    }

    private void checkRequiredSections(ParsedData data, List<Issue> issues) {
        String[] requiredSections = { "摘要", "引言", "正文", "结论", "参考文献" };

        for (String requiredSection : requiredSections) {
            boolean found = data.getSectionsList().stream()
                    .anyMatch(section -> section.getText().contains(requiredSection));

            if (!found) {
                Issue issue = createIntegrityIssue("ERR_INT_REQ_001",
                            "缺少必需章节：" + requiredSection,
                        0,
                            "请添加“" + requiredSection + "”章节",
                        "");
                issues.add(issue);
            }
        }
    }

    private void checkFigureTableNumbering(ParsedData data, List<Issue> issues) {
        int figureCount = 1;
        int tableCount = 1;

        for (Section section : data.getSectionsList()) {
            if ("figure".equals(section.getType())) {
                String sectionText = section.getText().toLowerCase();
                if (!sectionText.contains("图" + figureCount) &&
                        !sectionText.contains("figure " + figureCount)) {
                    Issue issue = createIntegrityIssue("ERR_INT_FIG_001",
                        "图编号不连续：应为图 " + figureCount,
                            section.getSectionId(),
                        "请按顺序重新编号图",
                            section.getText());
                    issues.add(issue);
                }
                figureCount++;
            } else if ("table".equals(section.getType())) {
                String sectionText = section.getText().toLowerCase();
                if (!sectionText.contains("表" + tableCount) &&
                        !sectionText.contains("table " + tableCount)) {
                    Issue issue = createIntegrityIssue("ERR_INT_TAB_001",
                        "表编号不连续：应为表 " + tableCount,
                            section.getSectionId(),
                        "请按顺序重新编号表",
                            section.getText());
                    issues.add(issue);
                }
                tableCount++;
            }
        }
    }

    private void checkDocumentStructure(ParsedData data, List<Issue> issues) {
        boolean hasAbstract = false;
        boolean hasConclusion = false;
        boolean hasReferences = false;

        for (Section section : data.getSectionsList()) {
            String text = section.getText().toLowerCase();
            if (text.contains("摘要") || text.contains("abstract")) {
                hasAbstract = true;
            }
            if (text.contains("结论") || text.contains("conclusion")) {
                hasConclusion = true;
            }
            if (text.contains("参考文献") || text.contains("references")) {
                hasReferences = true;
            }
        }

        if (hasAbstract && hasConclusion) {
            int abstractIndex = -1;
            int conclusionIndex = -1;

            for (int i = 0; i < data.getSectionsCount(); i++) {
                String text = data.getSections(i).getText().toLowerCase();
                if (text.contains("摘要") || text.contains("abstract")) {
                    abstractIndex = i;
                }
                if (text.contains("结论") || text.contains("conclusion")) {
                    conclusionIndex = i;
                }
            }

            if (abstractIndex > conclusionIndex) {
                Issue issue = createIntegrityIssue("ERR_INT_STRUCT_001",
                            "文档结构错误：摘要应位于结论之前",
                        0,
                            "请调整章节顺序，确保摘要位于结论之前",
                        "");
                issues.add(issue);
            }
        }

        if (!hasAbstract) {
            issues.add(createIntegrityIssue("ERR_INT_STRUCT_002",
                        "文档缺少摘要章节",
                    0,
                        "请添加摘要章节",
                    ""));
        }

        if (!hasConclusion) {
            issues.add(createIntegrityIssue("ERR_INT_STRUCT_003",
                        "文档缺少结论章节",
                    0,
                        "请添加结论章节",
                    ""));
        }

        if (!hasReferences) {
            issues.add(createIntegrityIssue("ERR_INT_STRUCT_004",
                        "文档缺少参考文献章节",
                    0,
                        "请添加参考文献章节",
                    ""));
        }
    }

    private Issue createIntegrityIssue(String code, String message,
            int sectionId, String suggestion,
            String originalSnippet) {
        return Issue.newBuilder()
                .setCode(code)
                .setMessage(message)
                .setSectionId(sectionId)
                .setSeverity(Severity.MEDIUM)
                .setSuggestion(suggestion)
                .setOriginalSnippet(
                        originalSnippet.length() > 100 ? originalSnippet.substring(0, 100) + "..." : originalSnippet)
                .build();
    }

    private Issue createErrorIssue(String code, String message,
            int sectionId, Severity severity) {
        return Issue.newBuilder()
                .setCode(code)
                .setMessage(message)
                .setSectionId(sectionId)
                .setSeverity(severity)
                    .setSuggestion("请检查文档或联系管理员")
                .setOriginalSnippet("")
                .build();
    }
}