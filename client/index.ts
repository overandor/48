// Simple Solana DEX client scaffold
import { Connection, PublicKey } from '@solana/web3.js';

const RPC_URL = process.env.RPC_URL || 'https://api.mainnet-beta.solana.com';

export const connection = new Connection(RPC_URL);

export async function getBalance(address: string) {
  const pubkey = new PublicKey(address);
  const balance = await connection.getBalance(pubkey);
  return balance / 1e9; // SOL
}

(async () => {
  const addr = process.env.TEST_WALLET || '';
  if (addr) {
    const bal = await getBalance(addr);
    console.log('Balance:', bal);
  }
})();
