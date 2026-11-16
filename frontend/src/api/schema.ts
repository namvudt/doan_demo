import { z } from "zod";

/*
 * FastAPI wire contracts.
 *
 * These schemas mirror api/schemas.py and the concrete response builders in
 * api/views.py. Keep them separate from the preview-only product models at the
 * bottom of this file: a guest API session is not a chat conversation, an
 * AssetView is not a heritage record, and a workflow stage is not necessarily
 * one model/tool call.
 */

const uuidSchema = z.string().uuid();
const dateTimeSchema = z.string().datetime({ offset: true });
const jsonObjectSchema = z.record(z.string(), z.unknown());

export const modelModeSchema = z.enum(["live", "demo"]);
export const executionStatusSchema = z.enum([
  "queued",
  "running",
  "cancel_requested",
  "succeeded",
  "failed",
  "cancelled",
  "awaiting_input",
]);
export const runKindSchema = z.enum(["full", "review", "clarification"]);
export const audienceSchema = z.enum(["tourist", "student"]);
export const feedbackRatingSchema = z.enum([
  "helpful",
  "needs_review",
  "unrated",
]);
export const roleSchema = z.enum([
  "coordinator",
  "visual",
  "knowledge",
  "generation",
  "aggregator",
  "judge",
]);

export const liveHealthSchema = z.object({ status: z.literal("ok") }).strict();
export const readyHealthSchema = z
  .object({
    status: z.enum(["ready", "worker_unavailable", "database_unavailable"]),
    database: z.boolean(),
    worker: z.boolean(),
    model_mode: modelModeSchema.optional(),
  })
  .strict();

export const sessionCreateSchema = z
  .object({ label: z.string().min(1).max(80).default("Frontend guest") })
  .strict();
export const sessionCreatedSchema = z
  .object({
    session_id: uuidSchema,
    access_token: z.string().min(1),
    token_type: z.literal("bearer"),
    expires_at: dateTimeSchema,
  })
  .strict();
export const sessionViewSchema = z
  .object({
    session_id: uuidSchema,
    label: z.string(),
    expires_at: dateTimeSchema,
  })
  .strict();

export const profileViewSchema = z
  .object({
    id: z.string(),
    workflow_version: z.string(),
    generation_enabled: z.boolean(),
  })
  .strict();
export const capabilitiesViewSchema = z
  .object({
    api_version: z.string(),
    config_hash: z.string(),
    model_mode: modelModeSchema,
    model_configured: z.boolean(),
    missing_roles: z.array(z.string()),
    max_upload_bytes: z.number().int().nonnegative(),
    max_image_pixels: z.number().int().nonnegative(),
    max_question_characters: z.number().int().positive(),
    profiles: z.array(profileViewSchema),
    session_bootstrap_required: z.boolean(),
    accuracy: z
      .object({
        enabled: z.boolean(),
        pilot_region: z.string(),
        max_clarifications: z.number().int().nonnegative(),
        budget: z
          .object({
            max_llm_calls: z.number().int().positive(),
            deadline_seconds: z.number().positive(),
            request_timeout_seconds: z.number().positive(),
          })
          .strict()
          .optional(),
        recognition: z
          .object({
            enabled: z.boolean(),
            min_observations: z.number().int().positive(),
            max_status: z.enum(["probable", "recognized"]),
          })
          .strict(),
      })
      .strict()
      .optional(),
    features: z
      .object({
        heritage_catalog: z.boolean().optional(),
        heritage_coordinates: z.boolean().optional(),
        heritage_media: z.boolean().optional(),
        heritage_asset_import: z.boolean().optional(),
      })
      .catchall(z.boolean())
      .optional(),
  })
  .strict();

export const stageDefinitionSchema = z
  .object({
    id: z.string(),
    title: z.string(),
    description: z.string(),
  })
  .strict();
export const workflowViewSchema = z
  .object({
    version: z.string(),
    stages: z.array(stageDefinitionSchema),
    diagram: z.string(),
  })
  .strict();

export const assetViewSchema = z
  .object({
    asset_id: uuidSchema,
    sha256: z.string(),
    size_bytes: z.number().int().nonnegative(),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    media_type: z.literal("image/png"),
    created_at: dateTimeSchema,
    content_url: z.string(),
  })
  .strict();
export const sampleViewSchema = z
  .object({ sample_id: z.string(), title: z.string() })
  .strict();
export const samplesViewSchema = z
  .object({ items: z.array(sampleViewSchema) })
  .strict();

export const heritageLocationSchema = z
  .object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
    verification_status: z.enum(["illustrative", "unverified", "verified"]),
    verification_note: z.string(),
    source_id: z.string().nullable().optional(),
  })
  .strict();
export const heritageMediaSchema = z
  .object({
    media_id: z.string().min(1),
    kind: z.literal("image"),
    url: z.string().min(1),
    alt: z.string(),
    caption: z.string(),
    verified: z.boolean(),
  })
  .strict();
export const heritageInformationSourceSchema = z
  .object({
    source_id: z.string().min(1),
    title: z.string(),
    publisher: z.string(),
    url: z.string(),
    kind: z.string(),
    summary: z.string(),
    verified: z.boolean(),
    verification_note: z.string(),
    index_status: z.literal("not_indexed"),
  })
  .strict();
export const heritageViewSchema = z
  .object({
    heritage_id: z.string().min(1),
    name: z.string().min(1),
    slug: z.string(),
    province: z.string(),
    address: z.string(),
    category: z.string(),
    period: z.string(),
    summary: z.string(),
    historical_information: z.string(),
    cultural_information: z.string(),
    tags: z.array(z.string()),
    location: heritageLocationSchema.nullable(),
    media: z.array(heritageMediaSchema),
    information_sources: z.array(heritageInformationSourceSchema),
    content_status: z.enum(["draft", "published"]),
    illustrative: z.boolean(),
    version: z.number().int().positive(),
    created_at: dateTimeSchema,
    updated_at: dateTimeSchema,
  })
  .strict();
export const heritagePageSchema = z
  .object({
    items: z.array(heritageViewSchema),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
    has_more: z.boolean(),
  })
  .strict();

export const focusBoxSchema = z
  .tuple([
    z.number().min(0).max(1),
    z.number().min(0).max(1),
    z.number().min(0).max(1),
    z.number().min(0).max(1),
  ])
  .refine(
    ([x1, y1, x2, y2]) => x1 < x2 && y1 < y2,
    "Vùng ảnh phải có diện tích dương.",
  );
export const locationHintSchema = z
  .object({
    name: z.string().trim().min(1).max(200),
    provenance: z.enum(["user", "sample_label"]).default("user"),
  })
  .strict();
export const requestedSlotSchema = z
  .object({
    slot_id: z.string(),
    question: z.string(),
    evidence_type: z.enum(["visual", "historical", "identity", "mixed"]),
  })
  .strict();
export const evidenceSchema = z
  .object({
    evidence_id: z.string(),
    kind: z.enum(["visual", "ocr", "source"]),
    text: z.string(),
    source_id: z.string().nullable().optional(),
    region_id: z.string().nullable().optional(),
    box: focusBoxSchema.nullable().optional(),
    version: z.string(),
    entity_id: z.string().nullable().optional(),
  })
  .strict();
export const checkedClaimSchema = z
  .object({
    claim_id: z.string(),
    slot_id: z.string(),
    text: z.string(),
    kind: z.enum(["visual", "historical", "interpretation", "identity"]),
    verdict: z.enum([
      "supported",
      "contradicted",
      "insufficient",
      "not_assessable",
    ]),
    evidence_ids: z.array(z.string()),
    quotations: z.array(
      z.object({ evidence_id: z.string(), quote: z.string() }).strict(),
    ),
    explanation: z.string(),
    risk_tags: z.array(
      z.enum(["han_nom_reading", "specific_material", "historical_date"]),
    ),
    gate_errors: z.array(z.string()),
  })
  .strict();
const recognitionAssessmentSchema = z
  .object({
    status: z.enum(["recognized", "probable", "ambiguous", "unrecognized"]),
    entity_id: z.string().nullable(),
    evidence_ids: z.array(z.string()),
    explanation: z.string(),
  })
  .strict();
export const recognitionSchema = recognitionAssessmentSchema
  .extend({
    name: z.string().nullable(),
    basis: z.string().nullable(),
    gate_errors: z.array(z.string()),
    candidate_support: z.array(jsonObjectSchema),
    assessment: recognitionAssessmentSchema.nullable(),
  })
  .strict();
export const clarificationSchema = z
  .object({
    clarification_id: z.string(),
    revision: z.number().int().positive(),
    reason: z.enum([
      "entity_ambiguous",
      "image_unreadable",
      "missing_evidence",
    ]),
    question: z.string(),
    options: z.array(z.string()),
    rounds: z.number().int().nonnegative(),
  })
  .strict();
export const clarificationBodySchema = z
  .object({
    clarification_id: z.string().min(1).max(100),
    revision: z.number().int().positive(),
    answer: z.string().max(2000).default(""),
    selected_candidate: z.string().min(1).max(200).nullable().optional(),
    asset_id: uuidSchema.nullable().optional(),
    focus_box: focusBoxSchema.nullable().optional(),
  })
  .strict()
  .refine(
    (body) =>
      Boolean(body.answer.trim() || body.selected_candidate || body.asset_id),
    "Hãy trả lời, chọn ứng viên hoặc bổ sung ảnh.",
  );
export const clarificationViewSchema = z
  .object({
    run_id: uuidSchema,
    execution_status: z.string(),
    clarification: clarificationSchema.nullable(),
    continuation_run_id: uuidSchema.nullable(),
  })
  .strict();
export const evidenceViewSchema = z
  .object({
    run_id: uuidSchema,
    result_schema_version: z.number().int(),
    answer_status: z.string().nullable(),
    recognition: recognitionSchema.nullable(),
    location_hint: locationHintSchema.nullable(),
    requested_slots: z.array(requestedSlotSchema),
    evidence: z.array(evidenceSchema),
    claims: z.array(checkedClaimSchema),
    candidates: z.array(jsonObjectSchema),
    image_quality: jsonObjectSchema,
    regions: z.array(jsonObjectSchema),
    tool_calls: z.array(jsonObjectSchema),
  })
  .strict();

export const runCreateSchema = z
  .object({
    asset_id: uuidSchema,
    question: z.string().trim().min(1).max(4000),
    audience: audienceSchema.default("tourist"),
    profile: z.literal("default").default("default"),
    parent_run_id: uuidSchema.nullable().optional(),
    conversation_id: uuidSchema.nullable().optional(),
    heritage_id: z.string().min(1).max(80).nullable().optional(),
    location_hint: locationHintSchema.nullable().optional(),
    focus_box: focusBoxSchema.nullable().optional(),
  })
  .strict();
export const runViewSchema = z
  .object({
    run_id: uuidSchema,
    run_kind: runKindSchema,
    request_id: z.string().nullable(),
    trace_id: uuidSchema.nullable(),
    asset_id: uuidSchema,
    parent_run_id: uuidSchema.nullable(),
    question: z.string(),
    audience: z.string(),
    model_mode: modelModeSchema,
    execution_status: executionStatusSchema,
    result_status: z.string().nullable(),
    bookmarked: z.boolean(),
    event_count: z.number().int().nonnegative(),
    error_type: z.string().nullable(),
    created_at: dateTimeSchema,
    started_at: dateTimeSchema.nullable(),
    finished_at: dateTimeSchema.nullable(),
    events_url: z.string(),
    result_url: z.string(),
  })
  .strict();
export const runPageSchema = z
  .object({
    items: z.array(runViewSchema),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
  })
  .strict();

export const eventViewSchema = z
  .object({
    sequence: z.number().int().positive(),
    event: z.string().min(1),
    data: jsonObjectSchema,
    created_at: dateTimeSchema,
  })
  .strict();
export const eventPageSchema = z
  .object({
    run_id: uuidSchema,
    items: z.array(eventViewSchema),
    next_after: z.number().int().nonnegative(),
    terminal: z.boolean(),
  })
  .strict();

export const retrievedSourceSchema = z
  .object({
    source_id: z.string().min(1),
    title: z.string().min(1),
    url: z.string().url(),
    type: z.enum(["wiki", "web", "maps"]),
    snippet: z.string(),
    retrieved_at: z.string().nullable(),
    revision_id: z.string().nullable(),
    content_hash: z.string().nullable().optional(),
    locator: z.string().nullable().optional(),
    publisher: z.string().nullable().optional(),
    annotation_status: z.enum(["retrieved", "draft", "reviewed"]).optional(),
    reviewer: z.string().nullable().optional(),
    reviewed_at: z.string().nullable().optional(),
    number: z.number().int(),
    cited: z.boolean(),
  })
  .strict();
export const resultViewSchema = z
  .object({
    result_schema_version: z.number().int().optional(),
    answer_status: z.string().nullable().optional(),
    recognition: recognitionSchema.nullable().optional(),
    location_hint: locationHintSchema.nullable().optional(),
    evidence: z.array(evidenceSchema).optional(),
    claims: z.array(checkedClaimSchema).optional(),
    requested_slots: z.array(requestedSlotSchema).optional(),
    candidates: z.array(jsonObjectSchema).optional(),
    image_quality: jsonObjectSchema.optional(),
    regions: z.array(jsonObjectSchema).optional(),
    tool_calls: z.array(jsonObjectSchema).optional(),
    clarification: clarificationSchema.nullable().optional(),
    run_id: uuidSchema,
    parent_run_id: uuidSchema.nullable(),
    run_kind: runKindSchema,
    reused_nodes: z.array(z.string()),
    upstream_config_hash: z.string().nullable(),
    model_mode: modelModeSchema,
    status: z.string(),
    question: z.string(),
    audience: z.string(),
    final_response: z.string().nullable(),
    sources: z.array(retrievedSourceSchema),
    plan: jsonObjectSchema,
    review: jsonObjectSchema,
    errors: z.array(jsonObjectSchema),
    duration: z.number(),
    usage: jsonObjectSchema,
    intermediate: jsonObjectSchema.nullable(),
  })
  .strict();
export const sourcesViewSchema = z
  .object({
    run_id: uuidSchema,
    items: z.array(retrievedSourceSchema),
  })
  .strict();
export const stepsViewSchema = z
  .object({
    run_id: uuidSchema,
    items: z.record(z.string(), jsonObjectSchema),
  })
  .strict();
export const metricsViewSchema = z
  .object({
    run_id: uuidSchema,
    model_mode: modelModeSchema,
    duration: z.number().nullable(),
    usage: jsonObjectSchema,
    calls: z.array(jsonObjectSchema),
    workflow_version: z.string(),
    config_hash: z.string(),
  })
  .strict();

export const feedbackBodySchema = z
  .object({
    rating: feedbackRatingSchema.default("unrated"),
    note: z.string().max(1500).default(""),
  })
  .strict();
export const bookmarkBodySchema = z.object({ saved: z.boolean() }).strict();

export const preflightBodySchema = z
  .object({
    roles: z
      .array(roleSchema)
      .min(1)
      .max(6)
      .default(["coordinator", "visual", "aggregator", "judge"]),
    force: z.boolean().default(false),
  })
  .strict();
export const roleReadinessSchema = z
  .object({
    role: z.string(),
    provider: z.string(),
    model: z.string(),
    ready: z.boolean(),
    cached: z.boolean(),
    checked_at: z.number().nullable(),
    error_type: z.string().nullable(),
    error_code: z.string().nullable(),
    error_category: z.string().nullable(),
    retryable: z.boolean(),
    provider_status_code: z.number().int().nullable(),
    provider_reason: z.string().nullable(),
  })
  .strict();
export const preflightViewSchema = z
  .object({
    ready: z.boolean(),
    roles: z.array(roleReadinessSchema),
    scope: z.string(),
    generation_verified: z.boolean(),
  })
  .strict();

export const errorDetailSchema = z
  .object({
    code: z.string(),
    message: z.string(),
    request_id: z.string(),
    details: jsonObjectSchema.nullable().optional(),
  })
  .strict();
export const errorResponseSchema = z
  .object({ error: errorDetailSchema })
  .strict();

export type ModelMode = z.infer<typeof modelModeSchema>;
export type ExecutionStatus = z.infer<typeof executionStatusSchema>;
export type RunKind = z.infer<typeof runKindSchema>;
export type Audience = z.infer<typeof audienceSchema>;
export type FeedbackRating = z.infer<typeof feedbackRatingSchema>;
export type WorkflowRole = z.infer<typeof roleSchema>;
export type LiveHealth = z.infer<typeof liveHealthSchema>;
export type ReadyHealth = z.infer<typeof readyHealthSchema>;
export type SessionCreateInput = z.input<typeof sessionCreateSchema>;
export type SessionCreated = z.infer<typeof sessionCreatedSchema>;
export type SessionView = z.infer<typeof sessionViewSchema>;
export type ProfileView = z.infer<typeof profileViewSchema>;
export type CapabilitiesView = z.infer<typeof capabilitiesViewSchema>;
export type StageDefinition = z.infer<typeof stageDefinitionSchema>;
export type WorkflowView = z.infer<typeof workflowViewSchema>;
export type AssetView = z.infer<typeof assetViewSchema>;
export type SampleView = z.infer<typeof sampleViewSchema>;
export type SamplesView = z.infer<typeof samplesViewSchema>;
export type HeritageView = z.infer<typeof heritageViewSchema>;
export type HeritagePage = z.infer<typeof heritagePageSchema>;
export type RunCreateInput = z.input<typeof runCreateSchema>;
export type RunView = z.infer<typeof runViewSchema>;
export type RunPage = z.infer<typeof runPageSchema>;
export type EventView = z.infer<typeof eventViewSchema>;
export type EventPage = z.infer<typeof eventPageSchema>;
export type RetrievedSource = z.infer<typeof retrievedSourceSchema>;
export type ResultView = z.infer<typeof resultViewSchema>;
export type EvidenceView = z.infer<typeof evidenceViewSchema>;
export type ClarificationView = z.infer<typeof clarificationViewSchema>;
export type Clarification = z.infer<typeof clarificationSchema>;
export type ClarificationInput = z.input<typeof clarificationBodySchema>;
export type SourcesView = z.infer<typeof sourcesViewSchema>;
export type StepsView = z.infer<typeof stepsViewSchema>;
export type MetricsView = z.infer<typeof metricsViewSchema>;
export type FeedbackBodyInput = z.input<typeof feedbackBodySchema>;
export type FeedbackBody = z.output<typeof feedbackBodySchema>;
export type BookmarkBody = z.infer<typeof bookmarkBodySchema>;
export type PreflightInput = z.input<typeof preflightBodySchema>;
export type RoleReadiness = z.infer<typeof roleReadinessSchema>;
export type PreflightView = z.infer<typeof preflightViewSchema>;
export type ErrorDetail = z.infer<typeof errorDetailSchema>;
export type ErrorResponse = z.infer<typeof errorResponseSchema>;
