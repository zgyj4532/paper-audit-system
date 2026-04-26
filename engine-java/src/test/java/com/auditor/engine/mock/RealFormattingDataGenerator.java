package com.auditor.engine.mock;

import com.auditor.grpc.*;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.Path;
import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONException;

public class RealFormattingDataGenerator {
    
    public static ParsedData generateRealFormattingData() throws JSONException, IOException {
        // Support Windows and Linux paths
        String jsonContent = loadJsonFile();
        JSONObject data = new JSONObject(jsonContent);
        
        ParsedData.Builder builder = ParsedData.newBuilder();
        builder.setDocId("real-thesis");
        
        // Set metadata
        DocumentMetadata.Builder metadataBuilder = DocumentMetadata.newBuilder();
        metadataBuilder.setTitle("虚拟现实三维全景仿真技术研究");
        metadataBuilder.setPageCount(26);
        builder.setMetadata(metadataBuilder.build());
        
        JSONArray sectionsArray = data.getJSONArray("sections");
        
        for (int i = 0; i < sectionsArray.length(); i++) {
            JSONObject sectionObj = sectionsArray.getJSONObject(i);
            
            Section.Builder sectionBuilder = Section.newBuilder();
            sectionBuilder.setSectionId(sectionObj.getInt("id"));
            sectionBuilder.setText(sectionObj.getString("text"));
            
            String type = sectionObj.getString("type");
            if ("heading".equals(type)) {
                sectionBuilder.setType("heading");
                sectionBuilder.setLevel(sectionObj.getInt("level"));
            } else {
                sectionBuilder.setType("paragraph");
                sectionBuilder.setLevel(0);
            }
            
            JSONObject props = sectionObj.getJSONObject("props");
            sectionBuilder.putProps("font-family", props.getString("font-family"));
            sectionBuilder.putProps("font-size", props.getString("font-size"));
            sectionBuilder.putProps("line-height", props.getString("line-height"));
            sectionBuilder.putProps("color", props.getString("color"));
            sectionBuilder.putProps("bold", String.valueOf(props.getBoolean("bold")));
            
            builder.addSections(sectionBuilder.build());
        }
        
        return builder.build();
    }
    
    /**
     * Load JSON file, support Windows and Linux paths
     */
    private static String loadJsonFile() throws IOException {
        // Try multiple possible paths
        String[] possiblePaths = {
            // Relative path (project root directory)
            "src/test/resources/real_formatting_data.json",
            // Absolute path (Linux)
            "/tmp/real_formatting_data.json",
            // Current working directory
            "real_formatting_data.json",
            // User home directory
            System.getProperty("user.home") + "/real_formatting_data.json"
        };
        
        for (String pathStr : possiblePaths) {
            Path path = Paths.get(pathStr);
            if (Files.exists(path)) {
                System.out.println("✓ Found test data file: " + path.toAbsolutePath());
                return new String(Files.readAllBytes(path));
            }
        }
        
        // If file not found, generate default data
        System.out.println("⚠ real_formatting_data.json not found, using default data");
        try {
            return generateDefaultJsonData();
        } catch (JSONException e) {
            throw new IOException("Failed to generate default data", e);
        }
    }
    
    /**
     * Generate default JSON test data
     */
    private static String generateDefaultJsonData() throws JSONException {
        JSONObject data = new JSONObject();
        JSONArray sections = new JSONArray();
        
        // Generate 26 sections (simulate 26-page thesis)
        for (int i = 1; i <= 26; i++) {
            JSONObject section = new JSONObject();
            section.put("id", i);
            section.put("text", "这是第 " + i + " 个章节的内容");
            section.put("type", i % 5 == 0 ? "heading" : "paragraph");
            section.put("level", i % 5 == 0 ? 1 : 0);
            
            JSONObject props = new JSONObject();
            props.put("font-family", i % 5 == 0 ? "黑体" : "宋体");
            props.put("font-size", i % 5 == 0 ? "16pt" : "12pt");
            props.put("line-height", "1.83");  // Line height is 1.83
            props.put("color", "black");
            props.put("bold", i % 5 == 0);
            
            section.put("props", props);
            sections.put(section);
        }
        
        data.put("sections", sections);
        return data.toString();
    }
}