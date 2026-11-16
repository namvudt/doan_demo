"""Published heritage catalog and server-authorized editorial writes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from api.catalog_schemas import Category, HeritagePage, HeritageView, HeritageWrite
from api.catalog_store import CatalogStore
from api.editorial_auth import editorial_dependency
from api.models import SessionToken
from api.runtime import Runtime
from api.schemas import AssetView
from api.store import StoreError
from api.views import asset_view


def catalog_router(settings, *, runtime_dependency, principal_dependency, operations_security):
    router = APIRouter(prefix="/api/v1", tags=["Catalog"])
    runtime = Annotated[Runtime, Depends(runtime_dependency)]
    owner = Annotated[SessionToken, Depends(principal_dependency)]

    editor = Annotated[
        str,
        Depends(
            editorial_dependency(
                settings,
                runtime_dependency,
                principal_dependency,
                operations_security,
                legacy_operations=True,
            )
        ),
    ]

    @router.get("/heritages", response_model=HeritagePage)
    def list_heritages(
        rt: runtime,
        q: Annotated[str, Query(max_length=200)] = "",
        province: Annotated[str | None, Query(max_length=120)] = None,
        category: Category | None = None,
        has_location: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return CatalogStore(rt.db).list_public(
            q=q,
            province=province,
            category=category,
            has_location=has_location,
            limit=limit,
            offset=offset,
        )

    @router.get("/heritages/{heritage_id}", response_model=HeritageView)
    def get_heritage(heritage_id: str, rt: runtime):
        return CatalogStore(rt.db).get_public(heritage_id)

    @router.get("/heritages/{heritage_id}/media/{media_id}/content")
    def media_content(heritage_id: str, media_id: str, rt: runtime):
        path = CatalogStore(rt.db).media_path(
            heritage_id, media_id, settings.catalog_media_dir, settings.data_dir / "catalog-media"
        )
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }[path.suffix.lower()]
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @router.post(
        "/heritages/{heritage_id}/media/{media_id}/assets",
        response_model=AssetView,
        status_code=201,
    )
    def import_media(heritage_id: str, media_id: str, current_owner: owner, rt: runtime):
        # The catalog photo becomes a normal owned asset. Catalog metadata is not
        # injected into a run or treated as retrieved/verified AI evidence.
        path = CatalogStore(rt.db).media_path(
            heritage_id, media_id, settings.catalog_media_dir, settings.data_dir / "catalog-media"
        )
        if path.stat().st_size > min(settings.max_upload_bytes, rt.config().max_image_bytes):
            raise StoreError(413, "image_too_large", "Image exceeds upload limit")
        return asset_view(rt.save_asset(current_owner.id, path.read_bytes()))

    @router.post(
        "/operations/heritages",
        response_model=HeritageView,
        status_code=201,
    )
    def create_heritage(body: HeritageWrite, rt: runtime, actor: editor):
        return CatalogStore(rt.db).create(body, actor=actor)

    @router.put(
        "/operations/heritages/{heritage_id}",
        response_model=HeritageView,
    )
    def replace_heritage(heritage_id: str, body: HeritageWrite, rt: runtime, actor: editor):
        return CatalogStore(rt.db).replace(heritage_id, body, actor=actor)

    return router
