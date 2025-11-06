# Polymarket PnL Calculator

Калькулятор прибыли/убытков по бинарным ставкам Polymarket с учётом комиссий.
Поддерживает ручной ввод параметров и *опциональный* OCR по скриншоту (если установлен Tesseract).

## Установка
```bash
pip install -r requirements.txt
```
> OCR-части нужны пакеты `pillow` и `pytesseract` и установленный локально Tesseract. Если OCR не нужен — можно не ставить.

## Запуск (ручной режим — рекомендуемый)
```bash
python polymarket_pnl_calculator.py --stake 500 --side yes --entry 0.43   --profit_fee_pct 0.02 --taker_fee_pct 0.0001 --gas 0.00 --output_dir reports
```

## Запуск (OCR по скриншоту)
```bash
python polymarket_pnl_calculator.py --stake 300 --side no --screenshot path/to/screen.png   --entry 0.57 --output_dir reports
```
> `--entry` лучше указывать явно: OCR может ошибаться.

## Параметры комиссий
- `--profit_fee_pct` — комиссия от **чистой прибыли** при выигрыше (0.02 = 2%).  
- `--taker_fee_pct` — такер-комиссия на нотационал (например 0.0001 = 0.01%).  
- `--trading_fee_pct` — если у тебя есть торговая комиссия на нотационал (по умолчанию 0).  
- `--gas` — фиксированный газ в USDC (по умолчанию 0).

## Вывод
Скрипт создаёт CSV и XLSX в папке `--output_dir` с подробной таблицей:
- Stake, Entry Price, Shares
- Win: Gross/Net Payout, Profit Fee, Entry Fees, Gas, Return %
- Lose: Net Loss, Return %
