package com.auditor.engine.service.checkers;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Page Margin Checker
 * 
 * Function: Check whether the page margins meet the standard (2.5cm on all sides)
 * Rule: Page margins must be 2.5cm
 * Severity: MEDIUM
 */
@Component
public class PageMarginChecker {
    
    private static final Logger logger = LoggerFactory.getLogger(PageMarginChecker.class);
    private static final float EXPECTED_MARGIN = 2.5f; // cm
    private static final float TOLERANCE = 0.1f; // Tolerance 0.1cm
    
    /**
     * Check page margins
     * 
     * @param data Parsed document data
     * @return List of detected issues
     */
    public List<Issue> checkPageMargins(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || !data.hasMetadata()) {
            logger.warn("Input data is null or missing metadata");
            return issues;
        }
        
        try {
            DocumentMetadata metadata = data.getMetadata();
            
            // Get margins directly from proto
            float topMargin = metadata.getMarginTop();
            float bottomMargin = metadata.getMarginBottom();
            
            // Check top margin
            if (topMargin > 0 && !isMarginValid(topMargin)) {
                Issue issue = Issue.newBuilder()
                        .setCode("FMT_MARGIN_001")
                    .setMessage("上边距应为 2.5cm，当前为 " + String.format("%.2f", topMargin) + "cm")
                        .setSeverity(Severity.MEDIUM)
                    .setSuggestion("将上边距调整为 2.5cm")
                        .build();
                issues.add(issue);
                logger.debug("Top margin issue found");
            }
            
            // Check bottom margin
            if (bottomMargin > 0 && !isMarginValid(bottomMargin)) {
                Issue issue = Issue.newBuilder()
                        .setCode("FMT_MARGIN_002")
                    .setMessage("下边距应为 2.5cm，当前为 " + String.format("%.2f", bottomMargin) + "cm")
                        .setSeverity(Severity.MEDIUM)
                    .setSuggestion("将下边距调整为 2.5cm")
                        .build();
                issues.add(issue);
                logger.debug("Bottom margin issue found");
            }
            
            logger.info("Page margin check completed, found {} issues", issues.size());
            
        } catch (Exception e) {
            logger.error("Page margin check exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_MARGIN_CHECK")
                    .setMessage("Page margin check exception: " + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
    
    /**
     * Check if margin is valid (within tolerance)
     */
    private boolean isMarginValid(float margin) {
        return Math.abs(margin - EXPECTED_MARGIN) <= TOLERANCE;
    }
}