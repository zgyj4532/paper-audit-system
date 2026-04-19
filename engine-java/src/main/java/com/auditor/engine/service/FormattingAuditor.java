package com.auditor.engine.service;

import com.auditor.grpc.*;
import com.auditor.engine.mock.MockDroolsEngine;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.ArrayList;

@Service
public class FormattingAuditor {

    private static final Logger logger = LoggerFactory.getLogger(FormattingAuditor.class);
    private KieContainer kieContainer;

    /** section pre-filtering service (stop detection + whitelist) */
    private final SectionFilterService sectionFilterService = new SectionFilterService();

    public FormattingAuditor() {
        try {
            KieServices kieServices = KieServices.Factory.get();
            kieContainer = kieServices.getKieClasspathContainer();
            logger.info("Formatting check rules engine initialized successfully");
        } catch (Exception e) {
            logger.warn("Drools rules engine initialization failed, using mock engine: {}", e.getMessage());
            kieContainer = null;
        }
    }

    public List<Issue> checkFormatting(ParsedData rawData) {
        List<Issue> issues = new ArrayList<>();

        if (rawData == null || rawData.getSectionsCount() == 0) {
            logger.warn("Input data is empty or has no sections");
            return issues;
        }

        // ── Pre-filter: truncate "Thesis Dataset" and subsequent sections ──
        ParsedData data = sectionFilterService.filterSections(rawData);
        logger.info("Formatting check section pre-filter: original {} → filtered {}",
                rawData.getSectionsCount(), data.getSectionsCount());

        // Use Drools if available, otherwise use mock engine
        if (kieContainer != null) {
            return checkFormattingWithDrools(data, issues);
        } else {
            logger.info("Using mock Drools engine for formatting check");
            return MockDroolsEngine.checkFormattingRules(data);
        }
    }
    
    private List<Issue> checkFormattingWithDrools(ParsedData data, List<Issue> issues) {
        KieSession kieSession = null;
        try {
            kieSession = kieContainer.newKieSession("formattingSession");

            kieSession.setGlobal("results", issues);
            kieSession.setGlobal("logger", logger);

            kieSession.insert(data);

            for (Section section : data.getSectionsList()) {
                kieSession.insert(section);
            }

            if (data.hasMetadata()) {
                kieSession.insert(data.getMetadata());
            }

            int firedRules = kieSession.fireAllRules();
            logger.info("Formatting check completed, fired {} rules, found {} issues",
                    firedRules, issues.size());

        } catch (Exception e) {
            logger.error("Formatting check execution exception", e);

            Issue errorIssue = Issue.newBuilder()
                    .setCode("RULE_ENGINE_ERROR")
                    .setMessage("Formatting check engine exception: " + e.getMessage())
                    .setSeverity(Severity.CRITICAL)
                    .build();
            issues.add(errorIssue);
        } finally {
            if (kieSession != null) {
                kieSession.dispose();
                logger.debug("KieSession resources released");
            }
        }

        return issues;
    }
}