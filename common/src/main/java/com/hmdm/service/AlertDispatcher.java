package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.AlertRule;
import com.hmdm.persistence.mapper.AlertRuleMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * <p>Matches a device event against the customer's {@link AlertRule}s and notifies each
 * matching rule's webhook and/or email — off the check-in request thread, so a slow or
 * unreachable webhook endpoint never delays a device's check-in response.</p>
 *
 * <p>Uses the JDK's built-in {@link HttpClient} (Java 11+, no new Maven dependency) and the
 * existing {@link EmailService} (already SMTP-configured from {@code .env}) — this class only
 * adds the matching + async dispatch, not a new transport.</p>
 */
@Singleton
public class AlertDispatcher {

    private static final Logger logger = LoggerFactory.getLogger(AlertDispatcher.class);
    private static final Duration WEBHOOK_TIMEOUT = Duration.ofSeconds(10);

    private final AlertRuleMapper alertRuleMapper;
    private final EmailService emailService;
    private final HttpClient httpClient;
    private final ExecutorService executor;

    @Inject
    public AlertDispatcher(AlertRuleMapper alertRuleMapper, EmailService emailService) {
        this.alertRuleMapper = alertRuleMapper;
        this.emailService = emailService;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(WEBHOOK_TIMEOUT)
                .build();
        // A handful of alerts per check-in cycle across a small fleet — a couple of threads is
        // plenty; this is not meant to scale to a high-volume notification pipeline.
        this.executor = Executors.newFixedThreadPool(2);
    }

    /**
     * Looks up matching rules for {@code (customerId, eventType)} and dispatches each,
     * asynchronously. Never throws — a lookup or dispatch failure is logged, not propagated,
     * since this must never fail (or slow down) the check-in it's called from.
     */
    public void dispatch(int customerId, String eventType, String deviceNumber, String detail) {
        if (eventType == null || eventType.isEmpty()) {
            return;
        }
        executor.submit(() -> {
            try {
                List<AlertRule> rules = alertRuleMapper.listMatching(customerId, eventType);
                for (AlertRule rule : rules) {
                    dispatchOne(rule, eventType, deviceNumber, detail);
                }
            } catch (Exception e) {
                logger.warn("Alert dispatch lookup failed for customer {} event {}: {}",
                        customerId, eventType, e.getMessage());
            }
        });
    }

    private void dispatchOne(AlertRule rule, String eventType, String deviceNumber, String detail) {
        String summary = "Device " + deviceNumber + " — " + eventType +
                (detail == null || detail.isEmpty() ? "" : ": " + detail);

        if (rule.getWebhookUrl() != null && !rule.getWebhookUrl().trim().isEmpty()) {
            try {
                String json = "{\"deviceNumber\":\"" + escape(deviceNumber) + "\"," +
                        "\"eventType\":\"" + escape(eventType) + "\"," +
                        "\"detail\":\"" + escape(detail == null ? "" : detail) + "\"," +
                        "\"ts\":" + System.currentTimeMillis() + "}";
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(rule.getWebhookUrl().trim()))
                        .timeout(WEBHOOK_TIMEOUT)
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(json))
                        .build();
                HttpResponse<Void> resp = httpClient.send(req, HttpResponse.BodyHandlers.discarding());
                if (resp.statusCode() >= 300) {
                    logger.warn("Webhook alert to {} returned status {}", rule.getWebhookUrl(), resp.statusCode());
                }
            } catch (Exception e) {
                logger.warn("Webhook alert to {} failed: {}", rule.getWebhookUrl(), e.getMessage());
            }
        }

        if (rule.getEmail() != null && !rule.getEmail().trim().isEmpty()) {
            try {
                emailService.sendEmail(rule.getEmail().trim(), "AMBIC MDM alert: " + eventType, summary);
            } catch (Exception e) {
                logger.warn("Email alert to {} failed: {}", rule.getEmail(), e.getMessage());
            }
        }
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
