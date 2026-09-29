package com.hmdm.rest.resource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Validates and normalises what the shop-side collector pushes, so the tablets only ever receive
 * a small, well-formed document regardless of what was posted. Rank is recomputed here (total
 * descending) rather than trusted, and the sentinel salesman "None" is dropped as a second guard.
 */
final class LeaderboardPayload {

    static final int MAX_BODY_CHARS = 32 * 1024;
    private static final int MAX_ENTRIES = 30;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    final String businessDate;
    final String generatedAt;
    final String json;

    private LeaderboardPayload(String businessDate, String generatedAt, String json) {
        this.businessDate = businessDate;
        this.generatedAt = generatedAt;
        this.json = json;
    }

    /** @return the normalised payload, or null when the body is not a usable leaderboard. */
    static LeaderboardPayload parse(String body) {
        if (body == null || body.length() > MAX_BODY_CHARS) return null;
        try {
            JsonNode root = MAPPER.readTree(body);
            JsonNode entries = root.get("entries");
            if (entries == null || !entries.isArray()) return null;

            ArrayNode clean = MAPPER.createArrayNode();
            long bills = 0;
            double amount = 0;
            java.util.List<ObjectNode> rows = new java.util.ArrayList<>();
            for (JsonNode e : entries) {
                String name = e.path("name").asText("").trim();
                if (name.isEmpty() || "none".equalsIgnoreCase(name) || name.length() > 80) continue;
                double total = e.path("total").asDouble(Double.NaN);
                int b = e.path("bills").asInt(-1);
                if (Double.isNaN(total) || Double.isInfinite(total) || b < 0) continue;
                ObjectNode row = MAPPER.createObjectNode();
                row.put("name", name);
                row.put("bills", b);
                row.put("total", Math.round(total * 100.0) / 100.0);
                rows.add(row);
            }
            rows.sort((x, y) -> Double.compare(y.get("total").asDouble(), x.get("total").asDouble()));
            int rank = 1;
            for (ObjectNode row : rows) {
                if (rank > MAX_ENTRIES) break;
                row.put("rank", rank++);
                clean.add(row);
                bills += row.get("bills").asLong();
                amount += row.get("total").asDouble();
            }

            String date = root.path("businessDate").asText("");
            if (!date.matches("\\d{4}-\\d{2}-\\d{2}")) return null;
            String generated = root.path("generatedAt").asText("");
            if (generated.length() > 40) generated = generated.substring(0, 40);

            ObjectNode out = MAPPER.createObjectNode();
            out.put("businessDate", date);
            out.put("generatedAt", generated);
            out.set("entries", clean);
            ObjectNode totals = out.putObject("totals");
            totals.put("salesmen", clean.size());
            totals.put("bills", bills);
            totals.put("amount", Math.round(amount * 100.0) / 100.0);
            return new LeaderboardPayload(date, generated, MAPPER.writeValueAsString(out));
        } catch (Exception ex) {
            return null;
        }
    }
}
