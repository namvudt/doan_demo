import type {
  PreviewContentSourceInput,
  PreviewFeedbackInput,
  PreviewFieldErrors,
  PreviewHeritageInput,
  PreviewLoginInput,
  PreviewRegistrationInput,
} from "./types";
import { PreviewValidationError } from "./types";

export type RegistrationField =
  "fullName" | "email" | "password" | "passwordConfirmation";
export type LoginField = "email" | "password";
export type HeritageField =
  | "name"
  | "slug"
  | "province"
  | "address"
  | "introduction"
  | "coordinates"
  | "media"
  | "sourceIds";
export type ContentSourceField =
  "heritageId" | "title" | "publisher" | "url" | "verificationNote";
export type FeedbackField = "runId" | "note";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const normalizePreviewEmail = (value: string) =>
  value.trim().toLocaleLowerCase("vi");

export const toPreviewSlug = (value: string) =>
  value
    .trim()
    .toLocaleLowerCase("vi")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);

const isSafeStaticMediaUrl = (value: string) =>
  /^\/(?!\/)[a-zA-Z0-9/_.,@+%()-]+$/.test(value);

const isSafeHttpUrl = (value: string) => {
  try {
    const url = new URL(value);
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      Boolean(url.hostname) &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
};

export function validatePreviewRegistration(
  input: PreviewRegistrationInput,
): PreviewFieldErrors<RegistrationField> {
  const errors: PreviewFieldErrors<RegistrationField> = {};
  const name = input.fullName.trim();
  const email = normalizePreviewEmail(input.email);

  if (name.length < 2 || name.length > 120)
    errors.fullName = "Họ tên cần từ 2 đến 120 ký tự.";
  if (!emailPattern.test(email) || email.length > 254)
    errors.email = "Nhập một địa chỉ email hợp lệ.";
  if (
    input.password.length < 8 ||
    !/[A-ZÀ-Ỹ]/u.test(input.password) ||
    !/[0-9]/.test(input.password)
  )
    errors.password =
      "Mật khẩu Preview cần ít nhất 8 ký tự, một chữ hoa và một chữ số.";
  if (input.passwordConfirmation !== input.password)
    errors.passwordConfirmation = "Mật khẩu xác nhận chưa khớp.";
  return errors;
}

export function validatePreviewLogin(
  input: PreviewLoginInput,
): PreviewFieldErrors<LoginField> {
  const errors: PreviewFieldErrors<LoginField> = {};
  if (!emailPattern.test(normalizePreviewEmail(input.email)))
    errors.email = "Nhập một địa chỉ email hợp lệ.";
  if (!input.password) errors.password = "Nhập mật khẩu UI Preview.";
  return errors;
}

export function validatePreviewHeritage(
  input: PreviewHeritageInput,
): PreviewFieldErrors<HeritageField> {
  const errors: PreviewFieldErrors<HeritageField> = {};
  const slug = input.slug
    ? toPreviewSlug(input.slug)
    : toPreviewSlug(input.name);

  if (input.name.trim().length < 2 || input.name.trim().length > 160)
    errors.name = "Tên di sản cần từ 2 đến 160 ký tự.";
  if (!slug) errors.slug = "Không thể tạo đường dẫn từ tên di sản.";
  if (input.province.trim().length < 2 || input.province.trim().length > 100)
    errors.province = "Tỉnh hoặc thành phố cần từ 2 đến 100 ký tự.";
  if (input.address.trim().length < 2 || input.address.trim().length > 300)
    errors.address = "Địa chỉ cần từ 2 đến 300 ký tự.";
  if (
    input.introduction.trim().length < 10 ||
    input.introduction.trim().length > 10_000
  )
    errors.introduction = "Giới thiệu cần từ 10 đến 10.000 ký tự.";

  if (input.coordinates) {
    const { latitude, longitude, verificationNote } = input.coordinates;
    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      latitude < -90 ||
      latitude > 90 ||
      longitude < -180 ||
      longitude > 180
    )
      errors.coordinates = "Vĩ độ hoặc kinh độ nằm ngoài phạm vi hợp lệ.";
    else if (!verificationNote.trim())
      errors.coordinates = "Cần ghi rõ chất lượng hoặc nguồn của tọa độ.";
  }

  if (input.media?.some((item) => !isSafeStaticMediaUrl(item.url)))
    errors.media =
      "Ảnh Preview phải dùng đường dẫn tĩnh cùng nguồn, ví dụ /demo-thap-rua.jpg.";
  if (
    input.sourceIds &&
    new Set(input.sourceIds).size !== input.sourceIds.length
  )
    errors.sourceIds = "Danh sách nguồn không được chứa ID trùng nhau.";
  return errors;
}

export function validatePreviewContentSource(
  input: PreviewContentSourceInput,
): PreviewFieldErrors<ContentSourceField> {
  const errors: PreviewFieldErrors<ContentSourceField> = {};
  if (!input.heritageId.trim()) errors.heritageId = "Chọn một hồ sơ di sản.";
  if (input.title.trim().length < 2 || input.title.trim().length > 240)
    errors.title = "Tên nguồn cần từ 2 đến 240 ký tự.";
  if (input.publisher.trim().length < 2 || input.publisher.trim().length > 160)
    errors.publisher = "Tên đơn vị xuất bản cần từ 2 đến 160 ký tự.";
  if (!isSafeHttpUrl(input.url))
    errors.url =
      "Nguồn phải là URL http/https hợp lệ và không chứa thông tin đăng nhập.";
  if (input.verified && !input.verificationNote?.trim())
    errors.verificationNote = "Nguồn đã xác minh cần có ghi chú đối chiếu.";
  return errors;
}

export function validatePreviewFeedback(
  input: PreviewFeedbackInput,
): PreviewFieldErrors<FeedbackField> {
  const errors: PreviewFieldErrors<FeedbackField> = {};
  if (!input.runId.trim()) errors.runId = "Thiếu mã lượt trả lời Preview.";
  if ((input.note || "").length > 1500)
    errors.note = "Ghi chú phản hồi không được quá 1.500 ký tự.";
  return errors;
}

export function throwIfPreviewInvalid<T extends string>(
  errors: PreviewFieldErrors<T>,
  message: string,
) {
  if (Object.keys(errors).length)
    throw new PreviewValidationError<T>(message, errors);
}
