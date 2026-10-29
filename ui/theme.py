"""Static styles only. User/model text is rendered through native Streamlit elements."""

import streamlit as st


def apply_theme():
    st.html(
        """<style>
      .block-container {max-width:1480px;padding-top:2rem;padding-bottom:3rem}
      .heritage-hero {background:linear-gradient(115deg,#133f32,#285c47);color:#fffdf5;
        border-radius:22px;padding:32px 36px;margin-bottom:26px;position:relative;overflow:hidden}
      .heritage-hero:after {content:'◈';position:absolute;right:35px;top:-25px;
        font-size:180px;color:#e7c282;opacity:.14;pointer-events:none}
      .heritage-hero .eyebrow {font-size:.76rem;letter-spacing:.2em;color:#efd49f;font-weight:700}
      .heritage-hero h1 {font-size:2.25rem;line-height:1.2;color:#fffdf5;margin:12px 0}
      .heritage-hero p {max-width:690px;color:#e5eee4;margin:0;line-height:1.6}
      .stage-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:12px 0}
      .stage-card {border:1px solid #d9dfd5;border-radius:12px;padding:12px;background:#fffdf7}
      .stage-card.running {border-color:#b88735;background:#fff3d9}
      .stage-card.completed {border-color:#7caa8d;background:#f0f8ef}
      .stage-card.failed {border-color:#cf8c7d;background:#fff0eb}
      .stage-card.skipped {background:#eeeee8;color:#646b62}
      .stage-card .stage-number {font-size:.72rem;letter-spacing:.12em;color:#657065}
      .stage-card strong {display:block;font-size:.9rem;margin:4px 0}
      .stage-card small {font-size:.76rem}
      [data-testid="stMetric"] {background:#f2f4eb;border:1px solid #dfe4d8;
        border-radius:12px;padding:14px}
      [data-testid="stTabs"] [data-baseweb="tab-list"] {gap:14px}
      @media(max-width:800px) {
        .heritage-hero {padding:24px}.heritage-hero h1 {font-size:1.7rem}
        .stage-grid {grid-template-columns:repeat(2,minmax(0,1fr))}
        .block-container {padding-top:4.5rem;padding-left:1rem;padding-right:1rem}
      }
    </style>
    <div class="heritage-hero">
      <div class="eyebrow">DI SẢN VIỆT NAM · KHÁM PHÁ QUA ẢNH</div>
      <h1>Mỗi bức ảnh, một câu chuyện di sản.</h1>
      <p>Quan sát kiến trúc, tìm hiểu lịch sử và đối chiếu tư liệu.
      Theo dõi từng bước để biết câu trả lời được hình thành từ đâu.</p>
    </div>""",
    )
