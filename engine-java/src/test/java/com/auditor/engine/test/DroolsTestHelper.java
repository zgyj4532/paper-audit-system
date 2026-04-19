package com.auditor.engine.test;

import org.kie.api.KieServices;
import org.kie.api.builder.KieBuilder;
import org.kie.api.builder.KieFileSystem;
import org.kie.api.builder.KieRepository;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * Drools test helper class, used to initialize the Drools rule engine in the test environment
 */
public class DroolsTestHelper {
    
    private static final Logger logger = LoggerFactory.getLogger(DroolsTestHelper.class);
    private static KieContainer kieContainer;
    
    /**
     * Initialize Drools rule engine
     */
    public static synchronized KieContainer initializeDrools() {
        if (kieContainer != null) {
            return kieContainer;
        }
        
        try {
            KieServices kieServices = KieServices.Factory.get();
            KieRepository kieRepository = kieServices.getRepository();
            KieFileSystem kfs = kieServices.newKieFileSystem();
            
            // Load all rule files
            loadRuleFiles(kfs);
            
            // Build KieModule
            KieBuilder kieBuilder = kieServices.newKieBuilder(kfs);
            kieBuilder.buildAll();
            
            if (kieBuilder.getResults().hasMessages()) {
                logger.error("Drools rule build failed:");
                kieBuilder.getResults().getMessages().forEach(msg -> 
                    logger.error("  - {}", msg.toString())
                );
                throw new RuntimeException("Drools rule build failed");
            }
            
            kieContainer = kieServices.newKieContainer(kieRepository.getDefaultReleaseId());
            logger.info("Drools rule engine initialized successfully");
            return kieContainer;
            
        } catch (Exception e) {
            logger.error("Drools initialization failed", e);
            throw new RuntimeException("Unable to initialize Drools", e);
        }
    }
    
    /**
     * Load rule files
     */
    private static void loadRuleFiles(KieFileSystem kfs) throws IOException {
        String[] rulePaths = {
            "src/main/resources/rules/formatting/formatting.drl",
            "src/main/resources/rules/reference/reference.drl",
            "src/main/resources/rules/integrity/integrity.drl"
        };
        
        for (String rulePath : rulePaths) {
            try {
                String content = new String(Files.readAllBytes(Paths.get(rulePath)));
                String resourcePath = "src/main/resources/" + rulePath.substring(rulePath.lastIndexOf("/") + 1);
                kfs.write(resourcePath, content);
                logger.debug("Rule file loaded: {}", rulePath);
            } catch (IOException e) {
                logger.warn("Unable to load rule file {}: {}", rulePath, e.getMessage());
            }
        }
    }
    
    /**
     * Create KieSession
     */
    public static KieSession createKieSession(String sessionName) {
        if (kieContainer == null) {
            initializeDrools();
        }
        return kieContainer.newKieSession(sessionName);
    }
    
    /**
     * Shutdown KieContainer
     */
    public static void shutdown() {
        if (kieContainer != null) {
            kieContainer.dispose();
            kieContainer = null;
        }
    }
}