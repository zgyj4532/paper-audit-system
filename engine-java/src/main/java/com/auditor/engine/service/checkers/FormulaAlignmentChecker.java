package com.auditor.engine.service.checkers;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Formula Alignment Checker
 * 
 * Function: Check if mathematical formulas are right-aligned
 * Rule: All formulas must be right-aligned
 * Severity: MEDIUM
 */
@Component
public class FormulaAlignmentChecker {
    
    private static final Logger logger = LoggerFactory.getLogger(FormulaAlignmentChecker.class);
    
    /**
     * Check formula alignment
     * 
     * @param data Parsed document data
     * @return List of found issues
     */
    public List<Issue> checkFormulaAlignment(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || data.getSectionsCount() == 0) {
            logger.warn("Input data is empty or has no sections");
            return issues;
        }
        
        try {
            for (Section section : data.getSectionsList()) {
                // Identify formula elements
                if ("formula".equals(section.getType())) {
                    String alignment = section.getPropsMap().getOrDefault("alignment", "left");
                    
                    // Check if right-aligned
                    if (!"right".equals(alignment) && !"center".equals(alignment)) {
                        Issue issue = Issue.newBuilder()
                                .setCode("FMT_FORMULA_001")
                                   .setMessage("公式对齐方式应为右对齐或居中")
                                .setSectionId(section.getSectionId())
                                .setSeverity(Severity.MEDIUM)
                                   .setSuggestion("请将公式对齐方式改为右对齐或居中")
                                .setOriginalSnippet(section.getText().length() > 100 ? 
                                    section.getText().substring(0, 100) + "..." : section.getText())
                                .build();
                        issues.add(issue);
                        logger.debug("Found formula alignment issue: {}", section.getSectionId());
                    }
                }
            }
            
            logger.info("Formula alignment check completed, found {} issues", issues.size());
            
        } catch (Exception e) {
            logger.error("Formula alignment check exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_FORMULA_CHECK")
                    .setMessage("Formula alignment check exception: " + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
}