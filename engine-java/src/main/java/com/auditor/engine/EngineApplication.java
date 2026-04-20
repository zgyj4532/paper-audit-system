package com.auditor.engine;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

/**
 * Spring Boot Startup Class
 * HTTP Port: controlled by ENGINE_JAVA_HTTP_PORT
 * gRPC Port: controlled by ENGINE_JAVA_GRPC_PORT (Managed by GrpcServer class)
 */
@SpringBootApplication
public class EngineApplication {
    private static final Logger logger = LoggerFactory.getLogger(EngineApplication.class);

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(EngineApplication.class);
        application.setWebApplicationType(WebApplicationType.SERVLET);

        ConfigurableApplicationContext context = application.run(args);

        String httpPort = context.getEnvironment().getProperty("ENGINE_JAVA_HTTP_PORT", "8081");
        String grpcPort = context.getEnvironment().getProperty("ENGINE_JAVA_GRPC_PORT", "9191");

        logger.info("AI Auditor Engine-Java started successfully!");
        logger.info("java engine listening on 127.0.0.1:{}", httpPort);
        logger.info("HTTP Service: http://localhost:{}", httpPort);
        logger.info("gRPC Service: localhost:{}", grpcPort);
    }
}