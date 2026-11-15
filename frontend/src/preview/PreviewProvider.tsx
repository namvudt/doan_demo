import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  PREVIEW_DEMO_ACCOUNTS,
  PREVIEW_GUEST_IDENTITY,
  PREVIEW_ROLE_USER_IDS,
  createPreviewInitialState,
} from "./fixtures";
import type {
  PreviewContentSource,
  PreviewContentSourceInput,
  PreviewContextValue,
  PreviewFeedback,
  PreviewFeedbackInput,
  PreviewFeedbackStatus,
  PreviewHeritage,
  PreviewHeritageInput,
  PreviewLoginInput,
  PreviewMedia,
  PreviewProviderProps,
  PreviewRegistrationInput,
  PreviewRole,
  PreviewState,
  PreviewUser,
  PreviewUserStatus,
} from "./types";
import { PreviewAuthorizationError, PreviewValidationError } from "./types";
import {
  normalizePreviewEmail,
  throwIfPreviewInvalid,
  toPreviewSlug,
  validatePreviewContentSource,
  validatePreviewFeedback,
  validatePreviewHeritage,
  validatePreviewLogin,
  validatePreviewRegistration,
} from "./validation";

const PreviewContext = createContext<PreviewContextValue | null>(null);

const ACTION_CLOCK_START = Date.parse("2026-11-15T12:00:00.000Z");

type Counters = {
  user: number;
  heritage: number;
  media: number;
  source: number;
  feedback: number;
};

const cloneState = (state: PreviewState): PreviewState =>
  structuredClone(state);

const initialCounters = (state: PreviewState): Counters => ({
  user: state.users.length + 1,
  heritage: state.heritages.length + 1,
  media:
    state.heritages.reduce((count, item) => count + item.media.length, 0) + 1,
  source: state.contentSources.length + 1,
  feedback: state.feedback.length + 1,
});

/** A deterministic, non-cryptographic preview verifier; never use it for real authentication. */
const previewPasswordFingerprint = (email: string, password: string) => {
  let hash = 0x811c9dc5;
  const value = `ui-preview-only:${normalizePreviewEmail(email)}:${password}`;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
};

const createSeedCredentialMap = () =>
  new Map(
    PREVIEW_DEMO_ACCOUNTS.map((account) => [
      normalizePreviewEmail(account.email),
      previewPasswordFingerprint(account.email, account.password),
    ]),
  );

const activeAdminCount = (users: PreviewUser[]) =>
  users.filter((user) => user.role === "admin" && user.status === "active")
    .length;

const currentIdentity = (state: PreviewState) =>
  state.currentUserId || PREVIEW_GUEST_IDENTITY;

export function PreviewProvider({
  children,
  initialState,
}: PreviewProviderProps) {
  const baseStateRef = useRef(
    cloneState(initialState || createPreviewInitialState()),
  );
  const [state, setState] = useState<PreviewState>(() =>
    cloneState(baseStateRef.current),
  );
  const stateRef = useRef(state);
  stateRef.current = state;
  const credentialFingerprints = useRef(createSeedCredentialMap());
  const counters = useRef(initialCounters(baseStateRef.current));
  const clock = useRef(0);

  const commit = useCallback(
    (update: (current: PreviewState) => PreviewState) => {
      const next = update(stateRef.current);
      stateRef.current = next;
      setState(next);
      return next;
    },
    [],
  );

  const nextTimestamp = useCallback(() => {
    clock.current += 1;
    return new Date(ACTION_CLOCK_START + clock.current * 1000).toISOString();
  }, []);

  const nextId = useCallback(
    (type: keyof Counters, prefix: string, existing: Iterable<string>) => {
      const occupied = new Set(existing);
      for (;;) {
        const candidate = `${prefix}-${String(counters.current[type]).padStart(3, "0")}`;
        counters.current[type] += 1;
        if (!occupied.has(candidate)) return candidate;
      }
    },
    [],
  );

  const requireAdmin = useCallback(() => {
    const current = stateRef.current.users.find(
      (user) => user.id === stateRef.current.currentUserId,
    );
    if (!current || current.role !== "admin" || current.status !== "active")
      throw new PreviewAuthorizationError(
        "Chỉ quản trị viên mô phỏng đang hoạt động mới có thể thực hiện thao tác này.",
      );
    return current;
  }, []);

  const login = useCallback(
    (input: PreviewLoginInput) => {
      throwIfPreviewInvalid(
        validatePreviewLogin(input),
        "Vui lòng kiểm tra thông tin đăng nhập UI Preview.",
      );
      const email = normalizePreviewEmail(input.email);
      const expected = credentialFingerprints.current.get(email);
      const supplied = previewPasswordFingerprint(email, input.password);
      const user = stateRef.current.users.find(
        (candidate) => normalizePreviewEmail(candidate.email) === email,
      );
      if (!user || !expected || expected !== supplied)
        throw new PreviewValidationError(
          "Email hoặc mật khẩu UI Preview không đúng.",
          { password: "Email hoặc mật khẩu UI Preview không đúng." },
          "PREVIEW_INVALID_CREDENTIALS",
        );
      if (user.status !== "active")
        throw new PreviewAuthorizationError(
          "Tài khoản mô phỏng này đang bị tạm khóa.",
        );
      commit((current) => ({ ...current, currentUserId: user.id }));
      return user;
    },
    [commit],
  );

  const register = useCallback(
    (input: PreviewRegistrationInput) => {
      throwIfPreviewInvalid(
        validatePreviewRegistration(input),
        "Vui lòng kiểm tra thông tin đăng ký UI Preview.",
      );
      const email = normalizePreviewEmail(input.email);
      if (
        stateRef.current.users.some(
          (user) => normalizePreviewEmail(user.email) === email,
        )
      )
        throw new PreviewValidationError(
          "Email này đã được dùng trong UI Preview.",
          { email: "Email này đã được dùng trong UI Preview." },
          "PREVIEW_EMAIL_EXISTS",
        );

      const timestamp = nextTimestamp();
      const user: PreviewUser = {
        id: nextId(
          "user",
          "preview-user",
          stateRef.current.users.map((item) => item.id),
        ),
        fullName: input.fullName.trim(),
        email,
        role: "user",
        status: "active",
        fictional: true,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      credentialFingerprints.current.set(
        email,
        previewPasswordFingerprint(email, input.password),
      );
      commit((current) => ({
        ...current,
        users: [...current.users, user],
        currentUserId: user.id,
      }));
      return user;
    },
    [commit, nextId, nextTimestamp],
  );

  const logout = useCallback(() => {
    commit((current) => ({ ...current, currentUserId: null }));
  }, [commit]);

  const switchRole = useCallback(
    (role: PreviewRole) => {
      const preferredId = PREVIEW_ROLE_USER_IDS[role];
      const user =
        stateRef.current.users.find(
          (candidate) =>
            candidate.id === preferredId &&
            candidate.role === role &&
            candidate.status === "active",
        ) ||
        stateRef.current.users.find(
          (candidate) =>
            candidate.role === role && candidate.status === "active",
        );
      if (!user)
        throw new PreviewValidationError(
          `Không còn tài khoản ${role} đang hoạt động trong UI Preview.`,
          {},
          "PREVIEW_ROLE_UNAVAILABLE",
        );
      commit((current) => ({ ...current, currentUserId: user.id }));
      return user;
    },
    [commit],
  );

  const updateProfile = useCallback(
    (input: { fullName: string }) => {
      const current = stateRef.current.users.find(
        (user) => user.id === stateRef.current.currentUserId,
      );
      if (!current)
        throw new PreviewAuthorizationError(
          "Hãy đăng nhập một tài khoản mô phỏng để cập nhật hồ sơ.",
        );
      const fullName = input.fullName.trim();
      if (fullName.length < 2 || fullName.length > 120)
        throw new PreviewValidationError("Họ tên cần từ 2 đến 120 ký tự.", {
          fullName: "Họ tên cần từ 2 đến 120 ký tự.",
        });
      const updated = {
        ...current,
        fullName,
        updatedAt: nextTimestamp(),
      };
      commit((snapshot) => ({
        ...snapshot,
        users: snapshot.users.map((user) =>
          user.id === current.id ? updated : user,
        ),
      }));
      return updated;
    },
    [commit, nextTimestamp],
  );

  const updateUserRole = useCallback(
    (userId: string, role: PreviewRole) => {
      requireAdmin();
      const user = stateRef.current.users.find((item) => item.id === userId);
      if (!user)
        throw new PreviewValidationError(
          "Không tìm thấy người dùng mô phỏng.",
          {},
          "PREVIEW_USER_NOT_FOUND",
        );
      if (
        user.role === "admin" &&
        role !== "admin" &&
        user.status === "active" &&
        activeAdminCount(stateRef.current.users) === 1
      )
        throw new PreviewValidationError(
          "UI Preview cần giữ lại ít nhất một quản trị viên đang hoạt động.",
          { role: "Không thể hạ quyền quản trị viên hoạt động cuối cùng." },
        );
      const timestamp = nextTimestamp();
      commit((current) => ({
        ...current,
        users: current.users.map((item) =>
          item.id === userId ? { ...item, role, updatedAt: timestamp } : item,
        ),
      }));
    },
    [commit, nextTimestamp, requireAdmin],
  );

  const updateUserStatus = useCallback(
    (userId: string, status: PreviewUserStatus) => {
      requireAdmin();
      const user = stateRef.current.users.find((item) => item.id === userId);
      if (!user)
        throw new PreviewValidationError(
          "Không tìm thấy người dùng mô phỏng.",
          {},
          "PREVIEW_USER_NOT_FOUND",
        );
      if (
        user.role === "admin" &&
        user.status === "active" &&
        status === "suspended" &&
        activeAdminCount(stateRef.current.users) === 1
      )
        throw new PreviewValidationError(
          "UI Preview cần giữ lại ít nhất một quản trị viên đang hoạt động.",
          { status: "Không thể khóa quản trị viên hoạt động cuối cùng." },
        );
      const timestamp = nextTimestamp();
      commit((current) => ({
        ...current,
        users: current.users.map((item) =>
          item.id === userId ? { ...item, status, updatedAt: timestamp } : item,
        ),
        currentUserId:
          userId === current.currentUserId && status === "suspended"
            ? null
            : current.currentUserId,
      }));
    },
    [commit, nextTimestamp, requireAdmin],
  );

  const toggleFavorite = useCallback(
    (heritageId: string) => {
      const heritage = stateRef.current.heritages.find(
        (item) => item.id === heritageId,
      );
      if (!heritage)
        throw new PreviewValidationError(
          "Không tìm thấy di sản mô phỏng.",
          {},
          "PREVIEW_HERITAGE_NOT_FOUND",
        );
      if (heritage.publicationStatus !== "published")
        throw new PreviewAuthorizationError(
          "Chỉ hồ sơ đã công bố mới có thể thêm vào mục yêu thích.",
        );
      commit((current) => {
        const identity = currentIdentity(current);
        const saved = current.favoriteHeritageIdsByIdentity[identity] || [];
        const exists = saved.includes(heritageId);
        return {
          ...current,
          favoriteHeritageIdsByIdentity: {
            ...current.favoriteHeritageIdsByIdentity,
            [identity]: exists
              ? saved.filter((id) => id !== heritageId)
              : [...saved, heritageId],
          },
        };
      });
    },
    [commit],
  );

  const normalizeMedia = useCallback(
    (items: PreviewHeritageInput["media"] = []): PreviewMedia[] => {
      const existing = stateRef.current.heritages.flatMap((heritage) =>
        heritage.media.map((item) => item.id),
      );
      return items.map((item) => ({
        ...item,
        id:
          item.id ||
          nextId("media", "preview-media", [
            ...existing,
            ...items.flatMap((candidate) => candidate.id || []),
          ]),
        alt: item.alt.trim(),
        caption: item.caption.trim(),
      }));
    },
    [nextId],
  );

  const validateHeritageRelations = useCallback(
    (input: PreviewHeritageInput, currentId?: string) => {
      const errors = validatePreviewHeritage(input);
      const slug = toPreviewSlug(input.slug || input.name);
      if (
        stateRef.current.heritages.some(
          (item) => item.slug === slug && item.id !== currentId,
        )
      )
        errors.slug = "Đường dẫn hồ sơ đã được dùng trong UI Preview.";
      const requestedSourceIds = input.sourceIds || [];
      const invalidSource = requestedSourceIds.find((sourceId) => {
        const source = stateRef.current.contentSources.find(
          (candidate) => candidate.id === sourceId,
        );
        return !source || !currentId || source.heritageId !== currentId;
      });
      if (invalidSource)
        errors.sourceIds = currentId
          ? `Nguồn ${invalidSource} không thuộc hồ sơ đang chỉnh sửa.`
          : "Hãy tạo hồ sơ trước, sau đó liên kết nguồn trong mục quản lý nguồn.";
      throwIfPreviewInvalid(errors, "Vui lòng kiểm tra hồ sơ di sản Preview.");
      return slug;
    },
    [],
  );

  const createHeritage = useCallback(
    (input: PreviewHeritageInput) => {
      requireAdmin();
      const slug = validateHeritageRelations(input);
      const timestamp = nextTimestamp();
      const heritage: PreviewHeritage = {
        id: nextId(
          "heritage",
          "preview-heritage",
          stateRef.current.heritages.map((item) => item.id),
        ),
        name: input.name.trim(),
        slug,
        province: input.province.trim(),
        address: input.address.trim(),
        category: input.category,
        period: (input.period || "").trim(),
        introduction: input.introduction.trim(),
        history: (input.history || "").trim(),
        culturalValue: (input.culturalValue || "").trim(),
        tags: Array.from(
          new Set((input.tags || []).map((tag) => tag.trim()).filter(Boolean)),
        ).slice(0, 20),
        coordinates: input.coordinates
          ? {
              ...input.coordinates,
              verificationNote: input.coordinates.verificationNote.trim(),
            }
          : null,
        media: normalizeMedia(input.media),
        sourceIds: [],
        publicationStatus: input.publicationStatus || "draft",
        illustrative: true,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      commit((current) => ({
        ...current,
        heritages: [...current.heritages, heritage],
      }));
      return heritage;
    },
    [
      commit,
      nextId,
      nextTimestamp,
      normalizeMedia,
      requireAdmin,
      validateHeritageRelations,
    ],
  );

  const updateHeritage = useCallback(
    (heritageId: string, input: PreviewHeritageInput) => {
      requireAdmin();
      const previous = stateRef.current.heritages.find(
        (item) => item.id === heritageId,
      );
      if (!previous)
        throw new PreviewValidationError(
          "Không tìm thấy di sản mô phỏng.",
          {},
          "PREVIEW_HERITAGE_NOT_FOUND",
        );
      const slug = validateHeritageRelations(input, heritageId);
      const updated: PreviewHeritage = {
        ...previous,
        name: input.name.trim(),
        slug,
        province: input.province.trim(),
        address: input.address.trim(),
        category: input.category,
        period: (input.period || "").trim(),
        introduction: input.introduction.trim(),
        history: (input.history || "").trim(),
        culturalValue: (input.culturalValue || "").trim(),
        tags: Array.from(
          new Set((input.tags || []).map((tag) => tag.trim()).filter(Boolean)),
        ).slice(0, 20),
        coordinates: input.coordinates
          ? {
              ...input.coordinates,
              verificationNote: input.coordinates.verificationNote.trim(),
            }
          : null,
        media: normalizeMedia(input.media),
        sourceIds: stateRef.current.contentSources
          .filter((source) => source.heritageId === heritageId)
          .map((source) => source.id),
        publicationStatus:
          input.publicationStatus || previous.publicationStatus,
        updatedAt: nextTimestamp(),
      };
      commit((current) => ({
        ...current,
        heritages: current.heritages.map((item) =>
          item.id === heritageId ? updated : item,
        ),
      }));
      return updated;
    },
    [
      commit,
      nextTimestamp,
      normalizeMedia,
      requireAdmin,
      validateHeritageRelations,
    ],
  );

  const deleteHeritage = useCallback(
    (heritageId: string) => {
      requireAdmin();
      if (!stateRef.current.heritages.some((item) => item.id === heritageId))
        throw new PreviewValidationError(
          "Không tìm thấy di sản mô phỏng.",
          {},
          "PREVIEW_HERITAGE_NOT_FOUND",
        );
      commit((current) => ({
        ...current,
        heritages: current.heritages.filter((item) => item.id !== heritageId),
        contentSources: current.contentSources.filter(
          (source) => source.heritageId !== heritageId,
        ),
        favoriteHeritageIdsByIdentity: Object.fromEntries(
          Object.entries(current.favoriteHeritageIdsByIdentity).map(
            ([identity, ids]) => [
              identity,
              ids.filter((id) => id !== heritageId),
            ],
          ),
        ),
      }));
    },
    [commit, requireAdmin],
  );

  const validateSourceRelations = useCallback(
    (input: PreviewContentSourceInput) => {
      const errors = validatePreviewContentSource(input);
      if (
        !stateRef.current.heritages.some(
          (heritage) => heritage.id === input.heritageId,
        )
      )
        errors.heritageId = "Không tìm thấy hồ sơ di sản mô phỏng.";
      throwIfPreviewInvalid(
        errors,
        "Vui lòng kiểm tra nguồn nội dung Preview.",
      );
    },
    [],
  );

  const createContentSource = useCallback(
    (input: PreviewContentSourceInput) => {
      requireAdmin();
      validateSourceRelations(input);
      const timestamp = nextTimestamp();
      const source: PreviewContentSource = {
        id: nextId(
          "source",
          "preview-source",
          stateRef.current.contentSources.map((item) => item.id),
        ),
        heritageId: input.heritageId,
        title: input.title.trim(),
        publisher: input.publisher.trim(),
        url: input.url.trim(),
        kind: input.kind,
        summary: (input.summary || "").trim(),
        verified: input.verified || false,
        verificationNote:
          input.verificationNote?.trim() ||
          "Chưa được biên tập viên xác minh trong UI Preview.",
        indexStatus: "not_indexed",
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      commit((current) => ({
        ...current,
        contentSources: [...current.contentSources, source],
        heritages: current.heritages.map((heritage) =>
          heritage.id === source.heritageId
            ? {
                ...heritage,
                sourceIds: Array.from(
                  new Set([...heritage.sourceIds, source.id]),
                ),
                updatedAt: timestamp,
              }
            : heritage,
        ),
      }));
      return source;
    },
    [commit, nextId, nextTimestamp, requireAdmin, validateSourceRelations],
  );

  const updateContentSource = useCallback(
    (sourceId: string, input: PreviewContentSourceInput) => {
      requireAdmin();
      validateSourceRelations(input);
      const previous = stateRef.current.contentSources.find(
        (item) => item.id === sourceId,
      );
      if (!previous)
        throw new PreviewValidationError(
          "Không tìm thấy nguồn nội dung mô phỏng.",
          {},
          "PREVIEW_SOURCE_NOT_FOUND",
        );
      const timestamp = nextTimestamp();
      const updated: PreviewContentSource = {
        ...previous,
        heritageId: input.heritageId,
        title: input.title.trim(),
        publisher: input.publisher.trim(),
        url: input.url.trim(),
        kind: input.kind,
        summary: (input.summary || "").trim(),
        verified: input.verified || false,
        verificationNote:
          input.verificationNote?.trim() ||
          "Chưa được biên tập viên xác minh trong UI Preview.",
        updatedAt: timestamp,
      };
      commit((current) => ({
        ...current,
        contentSources: current.contentSources.map((item) =>
          item.id === sourceId ? updated : item,
        ),
        heritages: current.heritages.map((heritage) => {
          const withoutSource = heritage.sourceIds.filter(
            (id) => id !== sourceId,
          );
          return heritage.id === updated.heritageId
            ? {
                ...heritage,
                sourceIds: [...withoutSource, sourceId],
                updatedAt: timestamp,
              }
            : heritage.sourceIds.includes(sourceId)
              ? {
                  ...heritage,
                  sourceIds: withoutSource,
                  updatedAt: timestamp,
                }
              : heritage;
        }),
      }));
      return updated;
    },
    [commit, nextTimestamp, requireAdmin, validateSourceRelations],
  );

  const deleteContentSource = useCallback(
    (sourceId: string) => {
      requireAdmin();
      if (!stateRef.current.contentSources.some((item) => item.id === sourceId))
        throw new PreviewValidationError(
          "Không tìm thấy nguồn nội dung mô phỏng.",
          {},
          "PREVIEW_SOURCE_NOT_FOUND",
        );
      const timestamp = nextTimestamp();
      commit((current) => ({
        ...current,
        contentSources: current.contentSources.filter(
          (item) => item.id !== sourceId,
        ),
        heritages: current.heritages.map((heritage) =>
          heritage.sourceIds.includes(sourceId)
            ? {
                ...heritage,
                sourceIds: heritage.sourceIds.filter((id) => id !== sourceId),
                updatedAt: timestamp,
              }
            : heritage,
        ),
      }));
    },
    [commit, nextTimestamp, requireAdmin],
  );

  const submitFeedback = useCallback(
    (input: PreviewFeedbackInput) => {
      throwIfPreviewInvalid(
        validatePreviewFeedback(input),
        "Vui lòng kiểm tra phản hồi Preview.",
      );
      const currentUser = stateRef.current.users.find(
        (user) => user.id === stateRef.current.currentUserId,
      );
      const timestamp = nextTimestamp();
      const previous = stateRef.current.feedback.find(
        (item) =>
          item.runId === input.runId.trim() &&
          item.userId === (currentUser?.id || null),
      );
      const feedback: PreviewFeedback = previous
        ? {
            ...previous,
            rating: input.rating,
            note: (input.note || "").trim(),
            status: "new",
            updatedAt: timestamp,
          }
        : {
            id: nextId(
              "feedback",
              "preview-feedback",
              stateRef.current.feedback.map((item) => item.id),
            ),
            runId: input.runId.trim(),
            userId: currentUser?.id || null,
            displayName: currentUser?.fullName || "Khách chưa đăng nhập",
            rating: input.rating,
            note: (input.note || "").trim(),
            status: "new",
            createdAt: timestamp,
            updatedAt: timestamp,
          };
      commit((current) => ({
        ...current,
        feedback: previous
          ? current.feedback.map((item) =>
              item.id === previous.id ? feedback : item,
            )
          : [...current.feedback, feedback],
      }));
      return feedback;
    },
    [commit, nextId, nextTimestamp],
  );

  const updateFeedbackStatus = useCallback(
    (feedbackId: string, status: PreviewFeedbackStatus) => {
      requireAdmin();
      if (!stateRef.current.feedback.some((item) => item.id === feedbackId))
        throw new PreviewValidationError(
          "Không tìm thấy phản hồi mô phỏng.",
          {},
          "PREVIEW_FEEDBACK_NOT_FOUND",
        );
      const timestamp = nextTimestamp();
      commit((current) => ({
        ...current,
        feedback: current.feedback.map((item) =>
          item.id === feedbackId
            ? { ...item, status, updatedAt: timestamp }
            : item,
        ),
      }));
    },
    [commit, nextTimestamp, requireAdmin],
  );

  const deleteFeedback = useCallback(
    (feedbackId: string) => {
      requireAdmin();
      if (!stateRef.current.feedback.some((item) => item.id === feedbackId))
        throw new PreviewValidationError(
          "Không tìm thấy phản hồi mô phỏng.",
          {},
          "PREVIEW_FEEDBACK_NOT_FOUND",
        );
      commit((current) => ({
        ...current,
        feedback: current.feedback.filter((item) => item.id !== feedbackId),
      }));
    },
    [commit, requireAdmin],
  );

  const resetPreview = useCallback(() => {
    const reset = cloneState(baseStateRef.current);
    stateRef.current = reset;
    setState(reset);
    credentialFingerprints.current = createSeedCredentialMap();
    counters.current = initialCounters(reset);
    clock.current = 0;
  }, []);

  const currentUser =
    state.users.find((user) => user.id === state.currentUserId) || null;
  const currentRole: PreviewRole = currentUser?.role || "guest";
  const favoriteHeritageIds = useMemo(
    () => state.favoriteHeritageIdsByIdentity[currentIdentity(state)] || [],
    [state],
  );
  const publishedHeritages = useMemo(
    () =>
      state.heritages.filter(
        (heritage) => heritage.publicationStatus === "published",
      ),
    [state.heritages],
  );
  const mappableHeritages = useMemo(
    () =>
      publishedHeritages.filter((heritage) => heritage.coordinates !== null),
    [publishedHeritages],
  );
  const roleVisibleHeritages = useMemo(
    () => (currentRole === "admin" ? state.heritages : publishedHeritages),
    [currentRole, publishedHeritages, state.heritages],
  );
  const favoriteHeritages = useMemo(
    () =>
      publishedHeritages.filter((heritage) =>
        favoriteHeritageIds.includes(heritage.id),
      ),
    [favoriteHeritageIds, publishedHeritages],
  );

  const value = useMemo<PreviewContextValue>(
    () => ({
      mode: "preview",
      state,
      currentUser,
      currentRole,
      isAuthenticated: currentUser !== null,
      heritages: roleVisibleHeritages,
      allHeritages: state.heritages,
      publishedHeritages,
      mappableHeritages,
      users: state.users,
      contentSources: state.contentSources,
      feedback: state.feedback,
      favoriteHeritageIds,
      favoriteHeritages,
      login,
      register,
      logout,
      switchRole,
      updateProfile,
      updateUserRole,
      updateUserStatus,
      toggleFavorite,
      createHeritage,
      updateHeritage,
      deleteHeritage,
      createContentSource,
      updateContentSource,
      deleteContentSource,
      submitFeedback,
      updateFeedbackStatus,
      deleteFeedback,
      resetPreview,
    }),
    [
      createContentSource,
      createHeritage,
      currentRole,
      currentUser,
      deleteContentSource,
      deleteFeedback,
      deleteHeritage,
      favoriteHeritageIds,
      favoriteHeritages,
      login,
      logout,
      mappableHeritages,
      publishedHeritages,
      register,
      resetPreview,
      roleVisibleHeritages,
      state,
      submitFeedback,
      switchRole,
      toggleFavorite,
      updateContentSource,
      updateFeedbackStatus,
      updateHeritage,
      updateProfile,
      updateUserRole,
      updateUserStatus,
    ],
  );

  return (
    <PreviewContext.Provider value={value}>{children}</PreviewContext.Provider>
  );
}

export function usePreview(): PreviewContextValue {
  const value = useContext(PreviewContext);
  if (!value)
    throw new Error("usePreview phải được dùng bên trong PreviewProvider.");
  return value;
}
