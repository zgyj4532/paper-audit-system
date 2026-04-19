package com.auditor.engine.service.checkers;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Header and Footer Checker
 * 
 * Function: Check whether the header contains the document title and the footer contains the page number
 * Rule: The header should contain the title, and the footer should contain the page number
 * Severity: LOW
 */
@Component
public class HeaderFooterChecker {
    
    private static final Logger logger = LoggerFactory.getLogger(HeaderFooterChecker.class);
    
    /**
     * Check header and footer
     * 
     * @param data Parsed document data
     * @return List of found issues
     */
    public List<Issue> checkHeaderFooter(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || !data.hasMetadata()) {
            logger.warn("Input data is null or missing metadata");
            return issues;
        }
        
        try {
            DocumentMetadata metadata = data.getMetadata();
            String title = metadata.getTitle();
            
            // Note: Since header and footer fields are not defined in proto,
            // only basic checks are performed here. In actual applications, header and footer information should be extracted from Sections
            
            if (title.isEmpty()) {
                logger.warn("Document title is empty, skipping header and footer check");
                return issues;
            }
            
            // Suggest adding header
            Issue headerIssue = Issue.newBuilder()
                    .setCode("FMT_HEADER_001")
                    .setMessage("建议在页眉中添加文档标题")
                    .setSeverity(Severity.LOW)
                    .setSuggestion("在页眉中添加文档标题：" + title)
                    .build();
            issues.add(headerIssue);
            logger.debug("Suggest adding header");
            
            // Suggest adding footer
            Issue footerIssue = Issue.newBuilder()
                    .setCode("FMT_FOOTER_001")
                    .setMessage("建议在页脚中添加页码")
                    .setSeverity(Severity.LOW)
                    .setSuggestion("在页脚中添加页码标记")
                    .build();
            issues.add(footerIssue);
            logger.debug("Suggest adding footer");
            
            logger.info("Header and footer check completed, found {} suggestions", issues.size());
            
        } catch (Exception e) {
            logger.error("Header and footer check exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_HEADER_FOOTER_CHECK")
                    .setMessage("页眉页脚检查异常：" + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .setSuggestion("请检查页眉页脚相关配置或源文档")
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
}