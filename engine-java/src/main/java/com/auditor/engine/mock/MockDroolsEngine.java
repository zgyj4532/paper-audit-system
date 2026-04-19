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
        
        // Rule 1: Level 1 headings must use SimHei font
        for (Section section : data.getSectionsList()) {
            if ("heading".equals(section.getType()) && section.getLevel() == 1) {
                String fontFamily = section.getPropsMap().get("font-family");
                if (fontFamily == null || (!fontFamily.contains("黑体") && !fontFamily.contains("SimHei") && !fontFamily.equals("黑体"))) {
                    issues.add(Issue.newBuilder()
                            .setCode("ERR_FONT_001")
                            .setMessage("一级标题必须使用黑体")
                            .setSectionId(section.getSectionId())
                            .setSeverity(Severity.MEDIUM)
                            .build());
                }
            }
            
            // Rule 2: Level 1 heading font size should be between 14-20pt
            if ("heading".equals(section.getType()) && section.getLevel() == 1) {
                String fontSize = section.getPropsMap().get("font-size");
                if (fontSize != null) {
                    try {
                        int size = Integer.parseInt(fontSize);
                        if (size < 14 || size > 20) {
                            issues.add(Issue.newBuilder()
                                    .setCode("ERR_SIZE_001")
                                    .setMessage("一级标题字号应在 14-20pt 之间")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.MEDIUM)
                                    .build());
                        }
                    } catch (NumberFormatException e) {
                        // Ignore unparseable font size
                    }
                }
            }
            
            // Rule 3: Level 2 heading font size should be between 12-18pt
            if ("heading".equals(section.getType()) && section.getLevel() == 2) {
                String fontSize = section.getPropsMap().get("font-size");
                if (fontSize != null) {
                    try {
                        int size = Integer.parseInt(fontSize);
                        if (size < 12 || size > 18) {
                            issues.add(Issue.newBuilder()
                                    .setCode("ERR_SIZE_002")
                                    .setMessage("二级标题字号应在 12-18pt 之间")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.LOW)
                                    .build());
                        }
                    } catch (NumberFormatException e) {
                        // Ignore
                    }
                }
            }
            
            // Rule 4: Body text font size should be 12pt
            if ("paragraph".equals(section.getType())) {
                String fontSize = section.getPropsMap().get("font-size");
                if (fontSize != null) {
                    try {
                        int size = Integer.parseInt(fontSize);
                        if (size != 12) {
                            issues.add(Issue.newBuilder()
                                    .setCode("ERR_SIZE_003")
                                    .setMessage("正文文字字号应为 12pt")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.LOW)
                                    .build());
                        }
                    } catch (NumberFormatException e) {
                        // Ignore
                    }
                }
            }
            
            // Rule 9: Check line spacing - fixed logic, line spacing should be >= 1.5
            String lineHeight = section.getPropsMap().get("line-height");
            if (lineHeight != null && !lineHeight.isEmpty()) {
                try {
                    float lineHeightValue = Float.parseFloat(lineHeight);
                    // Line spacing should not be less than 1.5, if less than 1.5 it's an issue
                    if (lineHeightValue < 1.5) {
                        issues.add(Issue.newBuilder()
                                .setCode("FMT_LINE_SPACING_001")
                                .setMessage("行距不应小于 1.5 倍")
                                .setSectionId(section.getSectionId())
                                .setSeverity(Severity.LOW)
                                .build());
                    }
                } catch (NumberFormatException e) {
                    // Ignore unparseable line spacing
                }
            }
        }
        
        return issues;
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
        int foundCount = 0;
        for (String required : requiredChapters) {
            boolean found = false;
            for (String chapter : chapters) {
                if (chapter.contains(required)) {
                    found = true;
                    foundCount++;
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