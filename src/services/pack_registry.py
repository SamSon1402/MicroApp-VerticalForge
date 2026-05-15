"""Pack registry — in-memory implementation.

Swap for a Postgres-backed implementation in production. Same interface, no
route changes required.
"""
from __future__ import annotations

from uuid import uuid4

from src.models.pack import Industry, PackDeployment, PackManifest, VerticalPack


class DuplicateVersionError(Exception):
    """Raised when publishing a (name, version) that already exists."""


class PackRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, VerticalPack] = {}
        self._deploys: dict[str, list[PackDeployment]] = {}  # pack_id -> deployments

    # -------------------------------------------------------- publish

    def publish(self, manifest: PackManifest) -> VerticalPack:
        # Idempotency: same (name, version) cannot be re-published
        for existing in self._packs.values():
            if (existing.manifest.name == manifest.name
                    and existing.manifest.version == manifest.version):
                raise DuplicateVersionError(
                    f"pack {manifest.name}@{manifest.version} already published",
                )
        pack = VerticalPack(
            pack_id=f"pack-{uuid4().hex[:10]}",
            manifest=manifest,
            published=True,
        )
        self._packs[pack.pack_id] = pack
        return pack

    # -------------------------------------------------------- query

    def get(self, pack_id: str) -> VerticalPack | None:
        return self._packs.get(pack_id)

    def list_packs(self, industry: Industry | None = None) -> list[VerticalPack]:
        packs = list(self._packs.values())
        if industry is not None:
            packs = [p for p in packs if p.manifest.industry == industry]
        return sorted(packs, key=lambda p: p.deploy_count, reverse=True)

    # -------------------------------------------------------- deployments

    def deploy(self, pack_id: str, tenant_id: str, params: dict[str, str]) -> PackDeployment:
        pack = self._packs.get(pack_id)
        if pack is None:
            raise KeyError(f"pack {pack_id} not found")
        deployment = PackDeployment(pack_id=pack_id, tenant_id=tenant_id, params=params)
        self._deploys.setdefault(pack_id, []).append(deployment)
        pack.deploy_count = len(self._deploys[pack_id])
        return deployment

    def deployments_for(self, pack_id: str) -> list[PackDeployment]:
        return list(self._deploys.get(pack_id, []))
