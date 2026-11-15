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
]);
export const runKindSchema = z.enum(["full", "review"]);
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

export const runCreateSchema = z
  .object({
    asset_id: uuidSchema,
    question: z.string().trim().min(1).max(4000),
    audience: audienceSchema.default("tourist"),
    profile: z.literal("default").default("default"),
    parent_run_id: uuidSchema.nullable().optional(),
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
    number: z.number().int(),
    cited: z.boolean(),
  })
  .strict();
export const resultViewSchema = z
  .object({
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
export type RunCreateInput = z.input<typeof runCreateSchema>;
export type RunView = z.infer<typeof runViewSchema>;
export type RunPage = z.infer<typeof runPageSchema>;
export type EventView = z.infer<typeof eventViewSchema>;
export type EventPage = z.infer<typeof eventPageSchema>;
export type RetrievedSource = z.infer<typeof retrievedSourceSchema>;
export type ResultView = z.infer<typeof resultViewSchema>;
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
