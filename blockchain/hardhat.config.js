import "@nomicfoundation/hardhat-toolbox";
import "dotenv/config";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Load accounts from accounts.json if it exists
 * Otherwise, use a single account from .env
 */
function loadAccounts() {
  const accountsPath = path.join(__dirname, "accounts.json");
  
  if (fs.existsSync(accountsPath)) {
    try {
      const accounts = JSON.parse(fs.readFileSync(accountsPath, "utf-8"));
      return accounts.map(acc => acc.privateKey);
    } catch (error) {
      console.warn("Failed to load accounts.json, falling back to .env");
    }
  }
  
  // Fallback to single account from .env
  return process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [];
}

const accounts = loadAccounts();

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  solidity: {
    version: "0.8.19",
    settings: {
      optimizer: {
        enabled: true,
        runs: 20
      },
      viaIR: true
    }
  },
  networks: {
    hardhat: {
      allowUnlimitedContractSize: true,
      accounts: {
        mnemonic: "test test test test test test test test test test test junk",
        path: "m/44'/60'/0'/0",
        initialIndex: 0,
        count: 20
      }
    },
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "https://sepolia.infura.io/v3/YOUR_INFURA_KEY",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
      chainId: 11155111
    },
    localhost: {
      url: "http://127.0.0.1:8545",
      accounts: accounts.length > 0 ? accounts : undefined,
      chainId: 31337
    }
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY
  },
  gasReporter: {
    enabled: process.env.REPORT_GAS !== undefined,
    currency: "USD"
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts"
  }
};
