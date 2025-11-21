Param(
  [string]$Repo = "achepw0wz/wowza-webhook-to-slack"
)
$ErrorActionPreference = "Stop"

Write-Host "Logging in to Docker Hub (repo: $Repo)"
docker login

Write-Host "Building local image (tag: $Repo:latest)"
docker build -t "$Repo:latest" .

Write-Host "Tagging production variant ($Repo:prod)"
docker tag "$Repo:latest" "$Repo:prod"

Write-Host "Pushing latest tag"
docker push "$Repo:latest"

Write-Host "Pushing prod tag"
docker push "$Repo:prod"

Write-Host "Done. Available tags: latest, prod"