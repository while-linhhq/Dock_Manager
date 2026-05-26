import type { SepayBankInfo } from '../services/revenueApi';

export function buildSepayQrUrl(
  bank: SepayBankInfo,
  amount: number,
  description: string,
): string {
  const params = new URLSearchParams({
    acc: bank.bank_account,
    bank: bank.bank_name,
    amount: String(Math.round(amount)),
    des: description,
  });
  return `https://qr.sepay.vn/img?${params.toString()}`;
}
