/**
 * Jest 配置（babel-jest + jsdom）
 *
 * 说明：next/jest 基于 SWC 原生转换，在部分环境下会触发原生崩溃（SIGBUS），
 * 因此这里使用纯 JS 的 babel 转换链，跨平台更稳。
 */
module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  testMatch: ["<rootDir>/__tests__/**/*.test.js"],
  transform: {
    "^.+\\.(js|jsx)$": [
      "babel-jest",
      {
        presets: [
          ["@babel/preset-env", { targets: { node: "current" } }],
          ["@babel/preset-react", { runtime: "automatic" }],
        ],
      },
    ],
  },
};
