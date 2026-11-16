import { Link } from "react-router-dom";
import { BookHeart, Heart, MessageSquareText } from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { Badge, Button, EmptyState, StatusCard } from "../ui/Ui";

export function FavoritesPage() {
  const app = useApp();
  const preview = usePreview();
  return (
    <div className="page-shell">
      <header className="page-heading">
        <div>
          <span className="eyebrow">MỤC ĐÃ LƯU</span>
          <h1>Những điều bạn muốn quay lại</h1>
          <p>Di sản yêu thích và run đã lưu là hai loại dữ liệu riêng biệt.</p>
        </div>
      </header>
      {app.mode === "preview" ? (
        <section>
          <div className="section-head">
            <div>
              <h2>Di sản yêu thích</h2>
              <p>
                Lưu trong bộ nhớ UI Preview, không đồng bộ tài khoản hay
                backend.
              </p>
            </div>
            <Badge tone="gold">Preview only</Badge>
          </div>
          {preview.favoriteHeritages.length ? (
            <div className="saved-list">
              {preview.favoriteHeritages.map((item) => (
                <article key={item.id}>
                  <div className="saved-icon">
                    <Heart size={19} fill="currentColor" />
                  </div>
                  <div>
                    <Link to={`/heritages/${item.id}`}>
                      <strong>{item.name}</strong>
                    </Link>
                    <p>
                      {item.province} · {item.introduction}
                    </p>
                  </div>
                  <Button
                    tone="ghost"
                    onClick={() => preview.toggleFavorite(item.id)}
                  >
                    Bỏ lưu
                  </Button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Chưa có di sản yêu thích"
              icon={<Heart size={27} />}
            >
              Mở thư viện và chọn biểu tượng trái tim trên một hồ sơ.{" "}
              <Link to="/heritages">Khám phá di sản</Link>
            </EmptyState>
          )}
        </section>
      ) : (
        <div className="favorites-sections">
          <section>
            <div className="section-head">
              <div>
                <h2>Di sản yêu thích</h2>
                <p>Đồng bộ theo tài khoản, tách biệt với run đã đánh dấu.</p>
              </div>
            </div>
            {!app.capabilities?.features?.heritage_favorites ? (
              <StatusCard
                kind="warning"
                title="Backend chưa cung cấp yêu thích di sản"
              />
            ) : !app.account ? (
              <EmptyState
                title="Cần tài khoản để lưu di sản"
                icon={<Heart size={27} />}
              >
                <Link to="/login">Đăng nhập tài khoản</Link> để đồng bộ di sản
                yêu thích.
              </EmptyState>
            ) : app.heritageFavoritesLoading ? (
              <StatusCard kind="loading" title="Đang tải di sản yêu thích…" />
            ) : app.heritageFavoritesError ? (
              <StatusCard kind="error" title="Không tải được di sản yêu thích">
                {app.heritageFavoritesError}
                <Button onClick={() => void app.refreshHeritageFavorites()}>
                  Thử lại
                </Button>
              </StatusCard>
            ) : app.heritageFavorites.length ? (
              <div className="saved-list">
                {app.heritageFavorites.map((item) => (
                  <article key={item.heritage_id}>
                    <div className="saved-icon">
                      <Heart size={19} fill="currentColor" />
                    </div>
                    <div>
                      <Link to={`/heritages/${item.heritage_id}`}>
                        <strong>{item.heritage.name}</strong>
                      </Link>
                      <p>
                        {item.heritage.province} · {item.heritage.summary}
                      </p>
                    </div>
                    <Button
                      tone="ghost"
                      onClick={() =>
                        void app
                          .setHeritageFavorite(item.heritage_id, false)
                          .catch((reason: unknown) =>
                            app.notify(
                              reason instanceof Error
                                ? reason.message
                                : "Không bỏ lưu được.",
                              "error",
                            ),
                          )
                      }
                    >
                      Bỏ lưu di sản
                    </Button>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Chưa có di sản yêu thích"
                icon={<Heart size={27} />}
              >
                <Link to="/heritages">Khám phá di sản</Link> và chọn biểu tượng
                trái tim để lưu.
              </EmptyState>
            )}
          </section>
          <section>
            <div className="section-head">
              <div>
                <h2>Run đã đánh dấu</h2>
                <p>
                  {app.account
                    ? "Những kết quả bạn đã đánh dấu được lưu theo tài khoản."
                    : "Những kết quả đã đánh dấu thuộc phiên khách hiện tại."}
                </p>
              </div>
              <Button tone="secondary" onClick={app.refreshSavedRuns}>
                Tải lại
              </Button>
            </div>
            {!app.apiSession ? (
              <EmptyState
                title="Cần phiên khách"
                icon={<BookHeart size={27} />}
              >
                Hãy <Link to="/login">truy cập phiên khách</Link> để xem run đã
                lưu.
              </EmptyState>
            ) : app.savedRunsLoading ? (
              <StatusCard kind="loading" title="Đang tải run đã lưu…" />
            ) : app.savedRunsError ? (
              <StatusCard kind="error" title="Không tải được run">
                {app.savedRunsError}
              </StatusCard>
            ) : app.savedRuns.length ? (
              <div className="saved-list">
                {app.savedRuns.map((run) => (
                  <article key={run.run_id}>
                    <div className="saved-icon">
                      <MessageSquareText size={19} />
                    </div>
                    <div>
                      <Link to={`/chat/runs/${run.run_id}`}>
                        <strong>{run.question}</strong>
                      </Link>
                      <p>
                        {run.execution_status} ·{" "}
                        {new Date(run.created_at).toLocaleString("vi-VN")}
                      </p>
                    </div>
                    <Badge
                      tone={
                        run.execution_status === "succeeded"
                          ? "green"
                          : "neutral"
                      }
                    >
                      {run.result_status || run.execution_status}
                    </Badge>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Chưa có run được đánh dấu"
                icon={<BookHeart size={27} />}
              >
                Mở một kết quả Chat rồi chọn “Lưu run”.
              </EmptyState>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
