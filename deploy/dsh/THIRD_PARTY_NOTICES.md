# DeepSeek Harness runtime notices

The LeadGen DSH image is built from DeepSeek Harness commit
`47f943859bef60e4160492346772ded9b24f765a`, licensed under MIT.
The complete upstream licence is copied into the image at
`/usr/share/licenses/dsh/UPSTREAM_LICENSE`.

The build materializes only the dependency closure declared in
`runtime.package.json`. `verify_runtime.mjs` records every packaged dependency's
name, version, and machine-readable licence in
`/usr/share/dsh/runtime-proof.json`; a missing or unknown licence fails the
image build. The CI SBOM is generated from the final distroless image, not from
the larger builder stage.

Build-only tooling:

- Node.js 24.9.0 builder image
- pnpm 11.7.0
- `@yao-pkg/pkg` 6.21.0

These tools are not present in the final runtime image.
