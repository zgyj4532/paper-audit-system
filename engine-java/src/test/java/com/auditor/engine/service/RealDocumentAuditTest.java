package com.auditor.engine.service;

import com.auditor.grpc.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.kie.api.KieServices;
import org.kie.api.runtime.KieContainer;
import org.kie.api.runtime.KieSession;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

/**
 * Windows environment adaptation version: Real document comprehensive audit test class
 * Fixed path escape causing [ERROR] illegal escape character error
 */
public class RealDocumentAuditTest {

    private static final Logger logger = LoggerFactory.getLogger(RealDocumentAuditTest.class);
    private ObjectMapper objectMapper = new ObjectMapper();
    private KieContainer kieContainer;

    @BeforeEach
    public void setUp() {
        try {
            KieServices kieServices = KieServices.Factory.get();
            kieContainer = kieServices.getKieClasspathContainer();
            logger.info("Drools rule container initialized successfully, preparing to load 56 rules");
        } catch (Exception e) {
            logger.error("Drools initialization failed, please check rule path or dependencies: {}", e.getMessage());
        }
    }

    @Test
    public void testFullDocumentAudit() throws IOException {
        // --- Fix point 1: Use forward slash '/' instead of backslash '\' to avoid escape errors ---
        // Cross-platform path: load real test data file from classpath
        java.net.URL resourceUrl = getClass().getClassLoader().getResource("data/audit_results_final.json");
        String jsonPath = resourceUrl != null ? resourceUrl.getFile() : 
            "src/test/resources/data/audit_results_final.json";
        
        File jsonFile = new File(jsonPath);
        if (!jsonFile.exists()) {
            logger.error("Parsed JSON file does not exist: {}", jsonPath);
            return;
        }

        JsonNode rootNode = objectMapper.readTree(jsonFile);
        ParsedData data = convertJsonToParsedData(rootNode);

        // 2. Collect all issues detected by rules
        List<Issue> allIssues = new ArrayList<>();

        // Execute three sessions in sequence, covering 56 rules
        auditWithSession("formattingSession", data, allIssues);
        auditWithSession("integritySession", data, allIssues);
        auditWithSession("referenceSession", data, allIssues);

        // 3. Build strictly aligned AuditResponse JSON structure
        ObjectNode responseNode = buildAuditResponse(allIssues);
        
        // --- Fix point 2: Also use forward slash and output path points to target directory ---
        String outputPath = "target/audit_results_final.json";
        
        String outputJson = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(responseNode);
        
        // Ensure output directory exists
        File outputFile = new File(outputPath);
        if (outputFile.getParentFile() != null) {
            outputFile.getParentFile().mkdirs();
        }

        Files.write(Paths.get(outputPath), outputJson.getBytes(StandardCharsets.UTF_8));
        
        logger.info("Comprehensive audit completed, total {} issues detected", allIssues.size());
        logger.info("Report generated at: {}", outputPath);
        System.out.println(outputJson);
    }

    private void auditWithSession(String sessionName, ParsedData data, List<Issue> results) {
        if (kieContainer == null) return;
        KieSession session = null;
        try {
            session = kieContainer.newKieSession(sessionName);
            if (session == null) {
                logger.warn("Cannot create session: {}, please check kmodule.xml configuration", sessionName);
                return;
            }
            
            session.setGlobal("results", results);
            session.setGlobal("logger", logger);

            session.insert(data);
            for (Section s : data.getSectionsList()) session.insert(s);
            for (Reference r : data.getReferencesList()) session.insert(r);
            if (data.hasMetadata()) session.insert(data.getMetadata());

            int fired = session.fireAllRules();
            logger.info("Session [{}] executed, triggered {} rules", sessionName, fired);
        } catch (Exception e) {
            logger.error("Session [{}] execution exception: {}", sessionName, e.getMessage());
        } finally {
            if (session != null) session.dispose();
        }
    }

    private ParsedData convertJsonToParsedData(JsonNode rootNode) {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId(rootNode.path("doc_id").asText("unknown"));

        JsonNode meta = rootNode.get("metadata");
        if (meta != null) {
            builder.setMetadata(DocumentMetadata.newBuilder()
                    .setTitle(meta.path("title").asText(""))
                    .setPageCount(meta.path("total_pages").asInt(0))
                    .build());
        }

        JsonNode sections = rootNode.get("sections");
        if (sections != null && sections.isArray()) {
            for (JsonNode sn : sections) {
                Section.Builder sb = Section.newBuilder()
                        .setSectionId(sn.path("section_id").asInt())
                        .setType(sn.path("type").asText("paragraph"))
                        .setLevel(sn.path("level").asInt(0))
                        .setText(sn.path("text").asText(""));
                
                JsonNode props = sn.get("properties");
                if (props != null) {
                    props.fields().forEachRemaining(e -> sb.putProps(e.getKey(), e.getValue().asText()));
                }
                builder.addSections(sb.build());
            }
        }

        if (rootNode.has("references")) {
            for (JsonNode rn : rootNode.get("references")) {
                builder.addReferences(Reference.newBuilder()
                        .setRefId(rn.path("ref_id").asText(""))
                        .setRawText(rn.path("raw_text").asText(""))
                        .build());
            }
        }
        return builder.build();
    }

    private ObjectNode buildAuditResponse(List<Issue> issues) {
        ObjectNode root = objectMapper.createObjectNode();
        ArrayNode issuesArray = root.putArray("issues");
        float totalScoreImpact = 0;

        for (Issue issue : issues) {
            ObjectNode item = issuesArray.addObject();
            item.put("type", issue.getCode());
            item.put("description", issue.getMessage());
            item.put("location", "Section ID: " + issue.getSectionId());
            item.put("suggestion", issue.getSuggestion());
            item.put("severity", issue.getSeverity().name());
            
            float impact = calculateImpact(issue.getSeverity());
            item.put("scoreImpact", impact);
            item.put("timestamp", System.currentTimeMillis());
            item.put("module", getModuleName(issue.getCode()));
            
            totalScoreImpact += impact;
        }

        root.put("scoreImpact", totalScoreImpact);
        return root;
    }

    private float calculateImpact(Severity s) {
        switch(s) {
            case CRITICAL: return 10.0f;
            case HIGH: return 5.0f;
            case MEDIUM: return 2.0f;
            case LOW: return 1.0f;
            default: return 0.0f;
        }
    }

    private String getModuleName(String code) {
        if (code.startsWith("FMT")) return "FormattingAuditor";
        if (code.startsWith("ERR_INT")) return "DocumentIntegrityScan";
        if (code.startsWith("ERR_REF")) return "ReferenceConsistencyChecker";
        return "GeneralAuditor";
    }
}