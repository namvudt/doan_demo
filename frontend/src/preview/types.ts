import type { ReactNode } from "react";

export type PreviewRole = "guest" | "user" | "admin";
export type PreviewUserStatus = "active" | "suspended";

export type PreviewHeritageCategory =
  "monument" | "temple" | "museum" | "archaeology";

export type PreviewPublicationStatus = "draft" | "published";
export type PreviewSourceKind = "official" | "unesco" | "reference" | "map";
export type PreviewFeedbackRating = "helpful" | "needs_review" | "unrated";
export type PreviewFeedbackStatus = "new" | "reviewed";

export interface PreviewCoordinates {
  latitude: number;
  longitude: number;
  /** Preview records must never imply that illustrative coordinates were verified. */
  verified: boolean;
  verificationNote: string;
}

export interface PreviewMedia {
  id: string;
  kind: "image";
  /** Root-relative URL to an asset shipped from frontend/public. */
  url: string;
  alt: string;
  caption: string;
  verified: boolean;
}

export type PreviewMediaInput = Omit<PreviewMedia, "id"> & { id?: string };

export interface PreviewHeritage {
  id: string;
  name: string;
  slug: string;
  province: string;
  address: string;
  category: PreviewHeritageCategory;
  period: string;
  introduction: string;
  history: string;
  culturalValue: string;
  tags: string[];
  coordinates: PreviewCoordinates | null;
  media: PreviewMedia[];
  sourceIds: string[];
  publicationStatus: PreviewPublicationStatus;
  /** Always true for records owned by this isolated UI Preview store. */
  illustrative: true;
  createdAt: string;
  updatedAt: string;
}

export interface PreviewHeritageInput {
  name: string;
  slug?: string;
  province: string;
  address: string;
  category: PreviewHeritageCategory;
  period?: string;
  introduction: string;
  history?: string;
  culturalValue?: string;
  tags?: string[];
  coordinates?: PreviewCoordinates | null;
  media?: PreviewMediaInput[];
  sourceIds?: string[];
  publicationStatus?: PreviewPublicationStatus;
}

export interface PreviewContentSource {
  id: string;
  heritageId: string;
  title: string;
  publisher: string;
  url: string;
  kind: PreviewSourceKind;
  summary: string;
  verified: boolean;
  verificationNote: string;
  /** This is catalog metadata, not proof of RAG ingestion or indexing. */
  indexStatus: "not_indexed";
  createdAt: string;
  updatedAt: string;
}

export interface PreviewContentSourceInput {
  heritageId: string;
  title: string;
  publisher: string;
  url: string;
  kind: PreviewSourceKind;
  summary?: string;
  verified?: boolean;
  verificationNote?: string;
}

export interface PreviewUser {
  id: string;
  fullName: string;
  email: string;
  role: PreviewRole;
  status: PreviewUserStatus;
  fictional: true;
  createdAt: string;
  updatedAt: string;
}

export interface PreviewRegistrationInput {
  fullName: string;
  email: string;
  password: string;
  passwordConfirmation: string;
}

export interface PreviewLoginInput {
  email: string;
  password: string;
}

export interface PreviewFeedback {
  id: string;
  runId: string;
  userId: string | null;
  displayName: string;
  rating: PreviewFeedbackRating;
  note: string;
  status: PreviewFeedbackStatus;
  createdAt: string;
  updatedAt: string;
}

export interface PreviewFeedbackInput {
  runId: string;
  rating: PreviewFeedbackRating;
  note?: string;
}

export interface PreviewState {
  users: PreviewUser[];
  heritages: PreviewHeritage[];
  contentSources: PreviewContentSource[];
  feedback: PreviewFeedback[];
  favoriteHeritageIdsByIdentity: Record<string, string[]>;
  currentUserId: string | null;
}

/** Works with both field-aware forms and generic Record<string, string> state. */
export type PreviewFieldErrors<T extends string = string> = Record<
  string,
  string
> &
  Partial<Record<T, string>>;

export class PreviewValidationError<T extends string = string> extends Error {
  constructor(
    message: string,
    public readonly fields: PreviewFieldErrors<T> = {},
    public readonly code = "PREVIEW_VALIDATION_ERROR",
  ) {
    super(message);
    this.name = "PreviewValidationError";
  }
}

export class PreviewAuthorizationError extends Error {
  readonly code = "PREVIEW_FORBIDDEN";

  constructor(
    message = "Bạn không có quyền thực hiện thao tác này trong UI Preview.",
  ) {
    super(message);
    this.name = "PreviewAuthorizationError";
  }
}

export interface PreviewContextValue {
  mode: "preview";
  state: PreviewState;
  currentUser: PreviewUser | null;
  currentRole: PreviewRole;
  isAuthenticated: boolean;
  /** Role-aware catalog: active admins see drafts; other roles see published records only. */
  heritages: PreviewHeritage[];
  /** Full shared catalog for explicitly guarded administration views. */
  allHeritages: PreviewHeritage[];
  publishedHeritages: PreviewHeritage[];
  mappableHeritages: PreviewHeritage[];
  users: PreviewUser[];
  contentSources: PreviewContentSource[];
  feedback: PreviewFeedback[];
  favoriteHeritageIds: string[];
  favoriteHeritages: PreviewHeritage[];
  login(input: PreviewLoginInput): PreviewUser;
  register(input: PreviewRegistrationInput): PreviewUser;
  logout(): void;
  /** Visible role switch for the explicitly labelled UI Preview environment. */
  switchRole(role: PreviewRole): PreviewUser;
  updateProfile(input: { fullName: string }): PreviewUser;
  updateUserRole(userId: string, role: PreviewRole): void;
  updateUserStatus(userId: string, status: PreviewUserStatus): void;
  toggleFavorite(heritageId: string): void;
  createHeritage(input: PreviewHeritageInput): PreviewHeritage;
  updateHeritage(
    heritageId: string,
    input: PreviewHeritageInput,
  ): PreviewHeritage;
  deleteHeritage(heritageId: string): void;
  createContentSource(input: PreviewContentSourceInput): PreviewContentSource;
  updateContentSource(
    sourceId: string,
    input: PreviewContentSourceInput,
  ): PreviewContentSource;
  deleteContentSource(sourceId: string): void;
  submitFeedback(input: PreviewFeedbackInput): PreviewFeedback;
  updateFeedbackStatus(feedbackId: string, status: PreviewFeedbackStatus): void;
  deleteFeedback(feedbackId: string): void;
  resetPreview(): void;
}

export interface PreviewProviderProps {
  children: ReactNode;
  initialState?: PreviewState;
}
