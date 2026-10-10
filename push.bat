
@echo off
title INKVOID GitHub Push
color 0A

cd /d "%~dp0"

echo.
echo ========================================
echo        INKVOID GitHub Push
echo ========================================
echo.

echo [1/3] 변경사항 추가 중...
git add .

echo.
echo [2/3] 커밋 생성 중...
set /p msg=커밋 메시지 입력 (엔터=Update): 

if "%msg%"=="" set msg=Update

git commit -m "%msg%"

echo.
echo [3/3] GitHub에 업로드 중...
git push

echo.
echo ========================================
echo              완료!
echo ========================================
echo.
pause

