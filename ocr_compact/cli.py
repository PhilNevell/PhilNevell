import os
import sys
import click

from .processing import ocr_pdf_to_compact


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--out-dir", default="./ocr_output", type=click.Path(file_okay=False), help="Directory to write outputs")
@click.option("--lang", default="eng", help="Tesseract language(s) e.g. 'eng' or 'eng+spa'")
@click.option("--dpi", default=300, show_default=True, help="Rasterization DPI for PDF pages")
@click.option("--conf-threshold", default=70, show_default=True, help="Confidence threshold (0-100) to crop and keep regions as images")
@click.option("--format", "fmt", type=click.Choice(["json", "md", "both"], case_sensitive=False), default="json", show_default=True, help="Output format")
@click.option("--embed-images/--no-embed-images", default=False, show_default=True, help="Embed crops as base64 data URIs instead of saving files")
@click.option("--max-webp-dim", default=1200, show_default=True, help="Max dimension for crop images (pixels)")
@click.option("--webp-quality", default=60, show_default=True, help="WEBP quality for crops (higher = larger file)")
def main(pdf_path: str, out_dir: str, lang: str, dpi: int, conf_threshold: int, fmt: str, embed_images: bool, max_webp_dim: int, webp_quality: int):
    os.makedirs(out_dir, exist_ok=True)
    out_path = ocr_pdf_to_compact(
        pdf_path=pdf_path,
        out_dir=out_dir,
        lang=lang,
        dpi=dpi,
        conf_threshold=conf_threshold,
        fmt=fmt.lower(),
        embed_images=embed_images,
        max_webp_dim=max_webp_dim,
        webp_quality=webp_quality,
    )
    click.echo(out_path)


if __name__ == "__main__":
    main()