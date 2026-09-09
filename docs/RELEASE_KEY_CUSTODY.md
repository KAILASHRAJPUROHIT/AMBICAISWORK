# Android release-key custody

The AMBIC MDM Device Owner agent must always be signed with the same release
certificate. Replacing that certificate after enrollment requires a factory
reset and reprovisioning of every enrolled tablet.

## Required custody

- The canonical key material is held in GitHub Actions repository secrets.
- A second encrypted/offline recovery copy is required before production
  enrollment. Store it with an owner-controlled password manager or offline
  encrypted storage; never commit it or place it in cloud file sync.
- Restrict repository admin and Actions-secret access to the minimum trusted
  owners. Review access quarterly and after staff changes.
- Never rotate the signing key for an ordinary release. Rotation is a device
  migration project, not a maintenance task.

## Required GitHub repository secrets

- `MDM_RELEASE_STORE_B64`
- `MDM_RELEASE_STORE_PASSWORD`
- `MDM_RELEASE_KEY_ALIAS`
- `MDM_RELEASE_KEY_PASSWORD`

The release workflow refuses to build a release without all four values.
