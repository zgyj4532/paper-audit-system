package com.auditor.engine.service.checkers;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Table Page Break Checker
 * 
 * Function: Check whether tables break across pages and whether there is a "continuation" flag
 * Rule: Tables that break across pages must be marked with "continuation"
 * Severity: HIGH
 */
@Component
public class TablePageBreakChecker {
    
    private static final Logger logger = LoggerFactory.getLogger(TablePageBreakChecker.class);
    
    /**
     * Check table page breaks
     * 
     * @param data Parsed document data
     * @return List of found issues
     */
    public List<Issue> checkTablePageBreak(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || data.getSectionsCount() == 0) {
            logger.warn("Input data is empty or has no sections");
            return issues;
        }
        
        try {
            for (Section section : data.getSectionsList()) {
                // Identify table elements
                if ("table".equals(section.getType())) {
                    String pageBreakStr = section.getPropsMap().getOrDefault("pageBreak", "false");
                    boolean pageBreak = Boolean.parseBoolean(pageBreakStr);
                    
                    // If the table breaks across pages, check for continuation flag
                    if (pageBreak) {
                        String continuationFlag = section.getPropsMap().get("continuationFlag");
                        String tableCaption = section.getPropsMap().get("caption");
                        
                        // Check if there is a continuation flag or the caption contains "续表"
                        boolean hasContinuationFlag = continuationFlag != null && !continuationFlag.isEmpty();
                        boolean captionHasContinuation = tableCaption != null && 
                            (tableCaption.contains("续表") || tableCaption.contains("continued"));
                        
                        if (!hasContinuationFlag && !captionHasContinuation) {
                            Issue issue = Issue.newBuilder()
                                    .setCode("FMT_TABLE_001")
                                    .setMessage("跨页表格必须标记为“续表”")
                                    .setSectionId(section.getSectionId())
                                    .setSeverity(Severity.HIGH)
                                    .setSuggestion("在表题或属性中添加“续表”标记")
                                    .setOriginalSnippet(section.getText().length() > 100 ? 
                                        section.getText().substring(0, 100) + "..." : section.getText())
                                    .build();
                            issues.add(issue);
                            logger.debug("Found table page break issue: {}", section.getSectionId());
                        }
                    }
                }
            }
            
            logger.info("Table page break check completed, found {} issues", issues.size());
            
        } catch (Exception e) {
            logger.error("Table page break check exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_TABLE_CHECK")
                    .setMessage("Table page break check exception: " + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
}