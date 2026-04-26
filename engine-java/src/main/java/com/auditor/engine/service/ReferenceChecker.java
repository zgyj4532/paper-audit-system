package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;

import java.util.List;
import java.util.ArrayList;

/**
 * Reference Checking Service
 * All checking logic is handled by the Drools rule engine
 * This class only calls the Drools engine and does not contain any hard-coded judgment logic
 */
@Service
public class ReferenceChecker {

    private static final Logger logger = LoggerFactory.getLogger(ReferenceChecker.class);
    private KieContainer kieContainer;

    /** section pre-filtering service (stop detection + whitelist) */
    private final SectionFilterService sectionFilterService = new SectionFilterService();

    public ReferenceChecker() {
        try {
            KieServices kieServices = KieServices.Factory.get();
            kieContainer = kieServices.getKieClasspathContainer();
            logger.info("Reference checking rule engine initialized successfully");
        } catch (Exception e) {
            logger.error("Drools rule engine initialization failed: {}", e.getMessage());
            kieContainer = null;
        }
    }

    /**
     * Check references
     * All checking logic is handled by rules in reference.drl
     */
    public List<Issue> checkReferences(ParsedData rawData) {
        List<Issue> issues = new ArrayList<>();

        if (rawData == null) {
            logger.error("Input data is null");
            return issues;
        }

        if (kieContainer == null) {
            logger.error("Drools rule engine not initialized");
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_ENGINE_INIT")
                    .setMessage("参考文献检查引擎未初始化")
                    .setSeverity(Severity.CRITICAL)
                    .build();
            issues.add(errorIssue);
            return issues;
        }

        // ── Pre-filter: truncate "Thesis Dataset" and subsequent sections ──
        ParsedData data = sectionFilterService.filterSections(rawData);
        logger.info("Reference checking section pre-filter: original {} → filtered {}",
                rawData.getSectionsCount(), data.getSectionsCount());

        // Use Drools for all reference checks
        return checkReferencesWithDrools(data, issues);
    }

    /**
     * Use Drools engine for reference checking
     * All judgment logic is defined in reference.drl
     */
    private List<Issue> checkReferencesWithDrools(ParsedData data, List<Issue> issues) {
        KieSession kieSession = null;
        try {
            kieSession = kieContainer.newKieSession("referenceSession");

            // Set global variables
            kieSession.setGlobal("results", issues);
            kieSession.setGlobal("logger", logger);

            // Insert data object
            kieSession.insert(data);

            // Insert all sections (for checking citation consistency)
            for (Section section : data.getSectionsList()) {
                kieSession.insert(section);
            }

            // Insert all references (for format checking)
            for (Reference ref : data.getReferencesList()) {
                kieSession.insert(ref);
            }

            // Fire all rules
            int firedRules = kieSession.fireAllRules();
            if (!issues.isEmpty()) {
                for (Issue issue : issues) {
                    logger.info("Reference check issue: code={}, message={}", issue.getCode(), issue.getMessage());
                }
            }
            logger.info("Reference checking completed, fired {} rules, found {} issues",
                    firedRules, issues.size());

        } catch (Exception e) {
            logger.error("Reference checking execution exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_REF_CHECK_EXCEPTION")
                    .setMessage("Reference checking exception: " + e.getMessage())
                    .setSeverity(Severity.CRITICAL)
                    .build();
            issues.add(errorIssue);
        } finally {
            if (kieSession != null) {
                kieSession.dispose();
                logger.debug("Reference checking KieSession disposed");
            }
        }

        return issues;
    }
}