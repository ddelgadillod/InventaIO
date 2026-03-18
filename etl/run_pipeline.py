#!/usr/bin/env python3
"""
InventAI/o — Pipeline ETL completo
====================================
Uso:
    python run_pipeline.py          # Pipeline completo (pasos 1-4)
    python run_pipeline.py --step 1 # Solo paso 1
    python run_pipeline.py --step 3 # Solo validación
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    parser = argparse.ArgumentParser(description="InventAI/o ETL Pipeline")
    parser.add_argument("--step", type=int, choices=[1, 2, 3, 4],
                        help="Ejecutar solo un paso específico")
    args = parser.parse_args()

    print("\n🚀 InventAI/o — Pipeline ETL de Bodega de Datos")
    start = time.time()

    pasos = {
        1: ("paso_01_transformar", "Transformar datos de Favorita"),
        2: ("paso_02_sinteticos", "Generar datos sintéticos"),
        3: ("paso_03_validar", "Validación de calidad"),
        4: ("paso_04_cargar", "Carga a PostgreSQL"),
    }

    steps_to_run = [args.step] if args.step else [1, 2, 3, 4]

    for step_num in steps_to_run:
        module_name, desc = pasos[step_num]
        print(f"\n{'=' * 60}")
        print(f"▶️  Paso {step_num}: {desc}")
        print(f"{'=' * 60}")

        module = __import__(module_name)
        result = module.run()

        if step_num == 3 and result is False:
            print("\n❌ Validación fallida. Corrija los errores antes de continuar.")
            sys.exit(1)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"✅ Pipeline completado en {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
