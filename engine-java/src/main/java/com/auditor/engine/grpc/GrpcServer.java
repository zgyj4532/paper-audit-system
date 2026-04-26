package com.auditor.engine.grpc;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.util.concurrent.Executors;

/**
 * gRPC Server Starter
 * Listening port: 9191
 *
 * Enabled features:
 *   - Java 21 Virtual Threads (newVirtualThreadPerTaskExecutor)
 *   - gRPC Server Reflection (ProtoReflectionService): enables grpcurl list
 */
@Component
public class GrpcServer {

    private static final Logger logger = LoggerFactory.getLogger(GrpcServer.class);
    private Server server;
    private final int port = resolvePort("ENGINE_JAVA_GRPC_PORT", 9191); // gRPC service listening port

    private static int resolvePort(String envName, int defaultPort) {
        try {
            String value = System.getenv(envName);
            if (value != null && !value.isBlank()) {
                return Integer.parseInt(value.trim());
            }
        } catch (Exception ignored) {
        }
        return defaultPort;
    }

    /**
     * Automatically start gRPC service after Spring Boot startup
     */
    @PostConstruct
    public void start() throws IOException {
        // Java 21 Virtual Threads: each gRPC request uses an independent virtual thread, supporting high concurrency auditing
        server = ServerBuilder.forPort(port)
                .addService(new DocumentAuditorServiceImpl())
                // gRPC Server Reflection: after registration, grpcurl list localhost:9191 can list all services
                .addService(ProtoReflectionService.newInstance())
                .executor(Executors.newVirtualThreadPerTaskExecutor())
                .build()
                .start();

        logger.info("gRPC Server started successfully, listening on port: {}", port);
        logger.info("Java 21 virtual thread pool enabled, supporting high concurrency audit requests");
        logger.info("gRPC Server Reflection enabled, use grpcurl list localhost:{} to view service list", port);
    }

    /**
     * Graceful shutdown before Spring Boot shutdown
     */
    @PreDestroy
    public void stop() {
        if (server != null) {
            logger.info("Shutting down gRPC Server...");
            server.shutdown();
            logger.info("gRPC Server has been shut down.");
        }
    }

    public void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        // Standalone run entry point
        GrpcServer server = new GrpcServer();
        server.start();
        server.blockUntilShutdown();
    }
}