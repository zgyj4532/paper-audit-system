package com.auditor.engine.grpc;

import com.auditor.grpc.*;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * gRPC Integration Test
 * Verify that after GrpcServer starts on port 9191, the client can successfully call the AuditRules interface
 */
public class GrpcIntegrationTest {

    private static final Logger logger = LoggerFactory.getLogger(GrpcIntegrationTest.class);
    private static GrpcServer grpcServer;
    private static ManagedChannel channel;
    private static DocumentAuditorGrpc.DocumentAuditorBlockingStub blockingStub;

    @BeforeAll
    public static void setup() throws IOException {
        // 1. Start the server
        grpcServer = new GrpcServer();
        grpcServer.start();

        // 2. Create client channel, connect to port 9191
        channel = ManagedChannelBuilder.forAddress("localhost", 9191)
                .usePlaintext()
                .build();

        // 3. Create blocking stub
        blockingStub = DocumentAuditorGrpc.newBlockingStub(channel);
    }

    @AfterAll
    public static void teardown() throws InterruptedException {
        if (channel != null) {
            channel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
        }
        if (grpcServer != null) {
            grpcServer.stop();
        }
    }

    @Test
    public void testAuditRulesRpc() {
        // Construct a simple request
        ParsedData data = ParsedData.newBuilder()
                .setDocId("test-doc-001")
                .setMetadata(DocumentMetadata.newBuilder().setTitle("测试文档").build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setType("heading")
                        .setLevel(1)
                        .setText("1. 错误标题")
                        .putProps("font-family", "SimSun") // Intentionally wrong, level 1 heading should be Heiti
                        .build())
                .build();

        AuditRequest request = AuditRequest.newBuilder()
                .setData(data)
                .setTargetRuleSet("GB/T7714")
                .build();

        // Initiate RPC call
        logger.info("Client initiates AuditRules RPC call (Port: 9191)...");
        AuditResponse response = blockingStub.auditRules(request);

        // Verify response
        assertNotNull(response);
        logger.info("Received RPC response, number of issues: {}, score impact: {}", response.getIssuesCount(), response.getScoreImpact());
        
        // Verify if typography error was detected
        boolean foundFontError = response.getIssuesList().stream()
                .anyMatch(issue -> issue.getCode().contains("FMT_HEADING_FONT"));
        
        assertTrue(foundFontError, "Level 1 heading font error should be detected");
    }
}