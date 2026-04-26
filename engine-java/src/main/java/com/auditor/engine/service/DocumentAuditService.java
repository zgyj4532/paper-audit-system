package com.auditor.engine.service;

import com.auditor.grpc.AuditResponse;
import com.auditor.grpc.Issue;
import com.auditor.grpc.ParsedData;
import com.auditor.grpc.Reference;
import com.auditor.grpc.Section;
import com.auditor.grpc.Severity;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class DocumentAuditService {

    private static final Logger logger = LoggerFactory.getLogger(DocumentAuditService.class);

    private final KieContainer kieContainer;
    private final SectionFilterService sectionFilterService = new SectionFilterService();

    public DocumentAuditService() {
        KieContainer container;
        try {
            KieServices kieServices = KieServices.Factory.get();
            container = kieServices.getKieClasspathContainer();
            logger.info("Document audit rule engine initialized successfully");
        } catch (Exception e) {
            logger.error("Drools rule engine initialization failed: {}", e.getMessage(), e);
            container = null;
        }
        this.kieContainer = container;
    }

    public AuditResponse audit(ParsedData rawData, String targetRuleSet) {
        List<Issue> issues = new ArrayList<>();

        if (rawData == null) {
            issues.add(buildErrorIssue("ERR_AUDIT_NULL", "Audit input is null", Severity.CRITICAL));
            return buildResponse(issues);
        }

        ParsedData data = sectionFilterService.filterSections(rawData);
        logger.info(
                "Audit request received, docId={}, targetRuleSet={}, originalSections={}, filteredSections={}",
                rawData.getDocId(),
                targetRuleSet,
                rawData.getSectionsCount(),
                data.getSectionsCount()
        );

        if (kieContainer == null) {
            issues.add(buildErrorIssue(
                    "ERR_ENGINE_INIT",
                    "文档审查引擎未初始化",
                    Severity.CRITICAL
            ));
            return buildResponse(issues);
        }

        try {
            auditWithSession("formattingSession", data, issues);
            auditWithSession("integritySession", data, issues);
            auditWithSession("referenceSession", data, issues);
            logger.info("Audit completed, total issues found: {}", issues.size());
        } catch (Exception e) {
            logger.error("Audit execution error", e);
            issues.add(buildErrorIssue(
                    "ERR_AUDIT_EXECUTION",
                    "Audit execution error: " + e.getMessage(),
                    Severity.HIGH
            ));
        }

        return buildResponse(issues);
    }

    private void auditWithSession(String sessionName, ParsedData data, List<Issue> results) {
        KieSession session = null;
        try {
            session = kieContainer.newKieSession(sessionName);
            if (session == null) {
                logger.warn("Unable to create session: {}, please check kmodule.xml configuration", sessionName);
                return;
            }

            session.setGlobal("results", results);
            session.setGlobal("logger", logger);

            session.insert(data);
            for (Section section : data.getSectionsList()) {
                session.insert(section);
            }
            for (Reference reference : data.getReferencesList()) {
                session.insert(reference);
            }
            if (data.hasMetadata()) {
                session.insert(data.getMetadata());
            }

            int fired = session.fireAllRules();
            logger.info("Session [{}] executed, fired {} rules", sessionName, fired);
        } catch (Exception e) {
            logger.error("Session [{}] execution error", sessionName, e);
            results.add(buildErrorIssue(
                    "ERR_SESSION_EXECUTION",
                    "Session [" + sessionName + "] execution error: " + e.getMessage(),
                    Severity.HIGH
            ));
        } finally {
            if (session != null) {
                session.dispose();
            }
        }
    }

    private AuditResponse buildResponse(List<Issue> issues) {
        return AuditResponse.newBuilder()
                .addAllIssues(issues)
                .setScoreImpact(calculateTotalScore(issues))
                .build();
    }

    private Issue buildErrorIssue(String code, String message, Severity severity) {
        return Issue.newBuilder()
                .setCode(code)
                .setMessage(message)
                .setSeverity(severity)
            .setSuggestion("请检查请求载荷或规则引擎配置")
                .setOriginalSnippet("")
                .build();
    }

    private float calculateTotalScore(List<Issue> issues) {
        float total = 0;
        for (Issue issue : issues) {
            switch (issue.getSeverity()) {
                case CRITICAL:
                    total += 10.0f;
                    break;
                case HIGH:
                    total += 5.0f;
                    break;
                case MEDIUM:
                    total += 2.0f;
                    break;
                case LOW:
                    total += 1.0f;
                    break;
                default:
                    break;
            }
        }
        return total;
    }
}