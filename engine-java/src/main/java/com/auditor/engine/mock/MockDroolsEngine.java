package com.auditor.engine.mock;

import com.auditor.grpc.*;
import java.util.*;
import java.util.regex.Pattern;

/**
 * Mock Drools engine implementation
 * Provides basic rule checking functionality when Drools cannot be initialized
 */
public class MockDroolsEngine {
    
    /**
     * Check formatting rules
     */
    public static List<Issue> checkFormattingRules(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || data.getSectionsList().isEmpty()) {
            return issues;
        }

        Deque<Integer> headingStack = new ArrayDeque<>();

        for (Section section : data.getSectionsList()) {
            String lineHeight = firstNonBlank(
                    section.getPropsMap().get("line-height"),
                    section.getPropsMap().get("line_spacing"),
                    section.getPropsMap().get("line-spacing"));
            if (lineHeight != null) {
                try {
                    double parsedLineHeight = Double.parseDouble(lineHeight);
                    if (Math.abs(parsedLineHeight - 1.5) > 0.05) {
                        issues.add(Issue.newBuilder()
                                .setCode("FMT_LINE_HEIGHT_001")
                                .setMessage("行距不应偏离 1.5 倍")
                                .setSectionId(section.getSectionId())
                                .setSeverity(Severity.MEDIUM)
                                .build());
                    }
                } catch (NumberFormatException ignored) {
                }
            }

            if ("heading".equals(section.getType())) {
                int level = section.getLevel();
                if (!headingStack.isEmpty() && level > headingStack.peek() + 1) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_HEADING_LEVEL_JUMP")
                            .setMessage("标题层级跳跃：从 level " + headingStack.peek() + " 到 level " + level)
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.HIGH)
                            .build());
                }
                while (!headingStack.isEmpty() && headingStack.peek() >= level) {
                    headingStack.pop();
                }
                headingStack.push(level);
            }

            if ("heading".equals(section.getType()) && section.getLevel() == 1) {
                String fontFamily = firstNonBlank(section.getPropsMap().get("font-family"), section.getPropsMap().get("font_family"));
                if (fontFamily == null || (!fontFamily.contains("黑体") && !fontFamily.contains("SimHei") && !fontFamily.contains("Hei") && !fontFamily.contains("hei"))) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_HEADING_FONT_001")
                            .setMessage("一级标题必须使用黑体")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.HIGH)
                            .build());
                }

                String fontSize = firstNonBlank(section.getPropsMap().get("font-size"), section.getPropsMap().get("font_size"));
                if (fontSize != null) {
                    try {
                        double size = Double.parseDouble(fontSize.replaceAll("[^0-9.]", ""));
                        if (Math.abs(size - 18) > 0.5) {
                            issues.add(Issue.newBuilder()
                                    .setCode("FMT_HEADING_SIZE_001")
                                    .setMessage("一级标题字号应为 18pt")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.MEDIUM)
                                    .build());
                        }
                    } catch (NumberFormatException ignored) {
                    }
                }
            }

            if ("heading".equals(section.getType()) && section.getLevel() == 2) {
                String fontFamily = firstNonBlank(section.getPropsMap().get("font-family"), section.getPropsMap().get("font_family"));
                if (fontFamily == null || (!fontFamily.contains("黑体") && !fontFamily.contains("SimHei") && !fontFamily.contains("Hei") && !fontFamily.contains("hei"))) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_HEADING_FONT_002")
                            .setMessage("二级标题必须使用黑体")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.HIGH)
                            .build());
                }

                String fontSize = firstNonBlank(section.getPropsMap().get("font-size"), section.getPropsMap().get("font_size"));
                if (fontSize != null) {
                    try {
                        double size = Double.parseDouble(fontSize.replaceAll("[^0-9.]", ""));
                        if (Math.abs(size - 16) > 1) {
                            issues.add(Issue.newBuilder()
                                    .setCode("FMT_HEADING_SIZE_002")
                                    .setMessage("二级标题字号应为 16pt")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.MEDIUM)
                                    .build());
                        }
                    } catch (NumberFormatException ignored) {
                    }
                }
            }

            if ("heading".equals(section.getType()) && section.getLevel() == 3) {
                String fontFamily = firstNonBlank(section.getPropsMap().get("font-family"), section.getPropsMap().get("font_family"));
                if (fontFamily == null || (!fontFamily.contains("黑体") && !fontFamily.contains("SimHei") && !fontFamily.contains("Hei") && !fontFamily.contains("hei"))) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_HEADING_FONT_003")
                            .setMessage("三级标题必须使用黑体")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.MEDIUM)
                            .build());
                }

                String fontSize = firstNonBlank(section.getPropsMap().get("font-size"), section.getPropsMap().get("font_size"));
                if (fontSize != null) {
                    try {
                        double size = Double.parseDouble(fontSize.replaceAll("[^0-9.]", ""));
                        if (Math.abs(size - 14) > 1) {
                            issues.add(Issue.newBuilder()
                                    .setCode("FMT_HEADING_SIZE_003")
                                    .setMessage("三级标题字号应为 14pt")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.MEDIUM)
                                    .build());
                        }
                    } catch (NumberFormatException ignored) {
                    }
                }
            }

            if ("paragraph".equals(section.getType())) {
                String fontFamily = firstNonBlank(section.getPropsMap().get("font-family"), section.getPropsMap().get("font_family"));
                if (fontFamily != null && !fontFamily.isEmpty()) {
                    if (!fontFamily.contains("SimSun") && !fontFamily.contains("Sun") && !fontFamily.contains("song") && !fontFamily.contains("Song") && !fontFamily.contains("宋体") && !fontFamily.contains("仿宋")) {
                        issues.add(Issue.newBuilder()
                                .setCode("FMT_BODY_FONT_001")
                                .setMessage("正文必须使用宋体/仿宋")
                                .setSectionId(section.getSectionId())
                                .setSeverity(Severity.MEDIUM)
                                .build());
                    }
                }

                String fontSize = firstNonBlank(section.getPropsMap().get("font-size"), section.getPropsMap().get("font_size"));
                if (fontSize != null && !fontSize.isEmpty()) {
                    try {
                        double size = Double.parseDouble(fontSize.replaceAll("[^0-9.]", ""));
                        if (Math.abs(size - 12) > 1) {
                            issues.add(Issue.newBuilder()
                                    .setCode("FMT_BODY_SIZE_001")
                                    .setMessage("正文字号应为 12pt")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.MEDIUM)
                                    .build());
                        }
                    } catch (NumberFormatException ignored) {
                    }
                }

                String indent = firstNonBlank(section.getPropsMap().get("first_line_indent"), section.getPropsMap().get("first-line-indent"));
                if (indent != null && !indent.isEmpty()) {
                    try {
                        double indentValue = Double.parseDouble(indent.replaceAll("[^0-9.]", ""));
                        if (indentValue < 1) {
                            issues.add(Issue.newBuilder()
                                    .setCode("FMT_INDENT_001")
                                    .setMessage("正文段落首行缩进不足")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.LOW)
                                    .build());
                        }
                    } catch (NumberFormatException ignored) {
                    }
                }
            }

            if ("formula".equals(section.getType())) {
                String alignment = firstNonBlank(section.getPropsMap().get("alignment"), section.getPropsMap().get("align"));
                if (alignment == null || !"right".equalsIgnoreCase(alignment)) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_FORMULA_ALIGNMENT")
                            .setMessage("公式必须右对齐")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.MEDIUM)
                            .build());
                }
            }

            if ("table".equals(section.getType())) {
                String pageBreak = firstNonBlank(section.getPropsMap().get("page-break"), section.getPropsMap().get("page_break"));
                String continueTableFlag = firstNonBlank(section.getPropsMap().get("continue-table-flag"), section.getPropsMap().get("continue_table_flag"));
                if ("true".equalsIgnoreCase(pageBreak) && !"true".equalsIgnoreCase(continueTableFlag)) {
                    issues.add(Issue.newBuilder()
                            .setCode("FMT_TABLE_PAGE_BREAK")
                            .setMessage("表格分页续表标记缺失")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.MEDIUM)
                            .build());
                }
            }
        }
        
        return issues;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.trim().isEmpty()) {
                return value.trim();
            }
        }
        return null;
    }
    
    /**
     * Check reference rules
     */
    public static List<Issue> checkReferenceRules(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null) {
            return issues;
        }
        
        // Extract all citations in the main text
        Set<String> citedReferences = new HashSet<>();
        Pattern refPattern = Pattern.compile("\\[(\\d+)\\]");
        
        for (Section section : data.getSectionsList()) {
            if ("paragraph".equals(section.getType())) {
                var matcher = refPattern.matcher(section.getText());
                while (matcher.find()) {
                    citedReferences.add("[" + matcher.group(1) + "]");
                }
            }
        }
        
        // Get the list of references
        Set<String> definedReferences = new HashSet<>();
        for (Reference ref : data.getReferencesList()) {
            definedReferences.add(ref.getRefId());
        }
        
        // Rule 1: Check missing references
        for (String cited : citedReferences) {
            if (!definedReferences.contains(cited)) {
                issues.add(Issue.newBuilder()
                        .setCode("ERR_REF_MISSING")
                        .setMessage("Reference " + cited + " is not defined at the end of the document")
                        .setSeverity(Severity.CRITICAL)
                        .build());
            }
        }
        
        // Rule 2: Check unused references
        for (String defined : definedReferences) {
            if (!citedReferences.contains(defined)) {
                issues.add(Issue.newBuilder()
                        .setCode("ERR_REF_UNUSED")
                        .setMessage("Reference " + defined + " is not cited in the main text")
                        .setSeverity(Severity.LOW)
                        .build());
            }
        }
        
        return issues;
    }
    
    /**
     * Check integrity rules
     */
    public static List<Issue> checkIntegrityRules(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || data.getSectionsList().isEmpty()) {
            return issues;
        }
        
        // Extract all chapter titles
        Set<String> chapters = new HashSet<>();
        int prevLevel = 0;
        Set<Integer> seenIds = new HashSet<>();
        
        for (Section section : data.getSectionsList()) {
            // Rule 1: Check duplicate section IDs
            if (seenIds.contains(section.getSectionId())) {
                issues.add(Issue.newBuilder()
                        .setCode("ERR_INTEGRITY_DUPLICATE")
                        .setMessage("Duplicate section ID: " + section.getSectionId())
                        .setSectionId(section.getSectionId())
                        .setSeverity(Severity.CRITICAL)
                        .build());
            }
            seenIds.add(section.getSectionId());
            
            if ("heading".equals(section.getType())) {
                chapters.add(section.getText());
                
                // Rule 2: Check heading level jumps
                if (prevLevel > 0 && section.getLevel() > prevLevel + 1) {
                    issues.add(Issue.newBuilder()
                            .setCode("ERR_INTEGRITY_HIER")
                            .setMessage("Heading level jump: from level " + prevLevel + " to level " + section.getLevel())
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.MEDIUM)
                            .build());
                }
                prevLevel = section.getLevel();
            }
        }
        
        // Rule 3: Check required chapters
        String[] requiredChapters = {"摘要", "引言", "正文", "结论", "参考文献"};
        for (String required : requiredChapters) {
            boolean found = false;
            for (String chapter : chapters) {
                if (chapter.contains(required)) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                issues.add(Issue.newBuilder()
                        .setCode("ERR_INTEGRITY_REQ_" + required)
                        .setMessage("缺少必需章节：" + required)
                        .setSeverity(Severity.CRITICAL)
                        .build());
            }
        }
        
        return issues;
    }
}