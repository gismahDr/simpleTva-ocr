from paddleocr import PaddleOCR

ocr = PaddleOCR(
    lang="fr",
    use_angle_cls=True
)

result = ocr.ocr("test.png")

for line in result:
    print(line)