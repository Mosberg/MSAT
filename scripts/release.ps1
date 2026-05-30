param(
    [string]$version = "0.1.0"
)

Write-Host "Preparing release $version"

python -m pip install --upgrade pip build
python -m build

Write-Host "Built distributions in dist/"
Write-Host "Next steps: git tag v$version && git push --tags && create a GitHub release attaching the artifacts in dist/"
