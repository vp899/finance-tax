/**
 * VoucherEditor + AccountCombobox 组件测试（智能补全、借贷平衡、保存载荷）
 */
import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import VoucherEditor, { AccountCombobox } from "@/components/VoucherEditor";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

const SUGGEST = {
  accounts: [
    { id: 1, code: "1002", name: "银行存款", is_leaf: true, direction: "D", balance: 5000 },
    { id: 2, code: "560204", name: "办公费", is_leaf: true, direction: "D", balance: 0 },
    { id: 3, code: "5602", name: "管理费用", is_leaf: false, direction: "D", balance: 100 },
  ],
  summaries: ["销售商品", "支付办公费"],
};

beforeEach(() => {
  global.fetch = jest.fn((url) => {
    const u = String(url);
    if (u.includes("/api/vouchers/suggest")) return Promise.resolve(okJson(SUGGEST));
    if (u.includes("/api/settings/voucher-types"))
      return Promise.resolve(okJson([{ name: "记账凭证", prefix: "记", is_default: true }]));
    if (u.includes("/api/vouchers")) return Promise.resolve(okJson({ id: 9, voucher_no: "记-202601-001" }));
    return Promise.resolve(okJson({}));
  });
});

afterEach(() => jest.restoreAllMocks());

describe("AccountCombobox 智能补全", () => {
  test("聚焦后展示科目下拉", async () => {
    render(<AccountCombobox onSelect={() => {}} />);
    fireEvent.focus(screen.getByPlaceholderText("输入编码/名称/拼音首字母"));
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    expect(screen.getByText("办公费")).toBeInTheDocument();
  });

  test("点击科目回填输入框并回调", async () => {
    const onSelect = jest.fn();
    render(<AccountCombobox onSelect={onSelect} />);
    fireEvent.focus(screen.getByPlaceholderText("输入编码/名称/拼音首字母"));
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByText("银行存款"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ code: "1002" }));
  });

  test("非末级科目有醒目标记", async () => {
    render(<AccountCombobox onSelect={() => {}} />);
    fireEvent.focus(screen.getByPlaceholderText("输入编码/名称/拼音首字母"));
    await waitFor(() => expect(screen.getByText("管理费用")).toBeInTheDocument());
    expect(screen.getByText("（非末级）")).toBeInTheDocument();
  });

  test("键盘上下+回车选择", async () => {
    const onSelect = jest.fn();
    render(<AccountCombobox onSelect={onSelect} />);
    const input = screen.getByPlaceholderText("输入编码/名称/拼音首字母");
    fireEvent.focus(input);
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ code: "560204" }));
  });

  test("输入触发搜索请求（拼音）", async () => {
    render(<AccountCombobox onSelect={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("输入编码/名称/拼音首字母"), {
      target: { value: "yhck" },
    });
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("q=yhck"),
        expect.anything()
      )
    );
  });
});

describe("VoucherEditor 凭证编辑", () => {
  test("初始渲染两行空分录", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("等待录入…")).toBeInTheDocument();
  });

  test("录入金额后提示借贷不平衡", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[0], { target: { value: "100" } });
    expect(screen.getByText(/借贷不平衡/)).toBeInTheDocument();
  });

  test("借贷相等时提示平衡", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    const [d1, , , c2] = screen.getAllByPlaceholderText("0.00");
    fireEvent.change(d1, { target: { value: "100" } });
    fireEvent.change(c2, { target: { value: "100" } });
    expect(screen.getByText("✓ 借贷平衡")).toBeInTheDocument();
  });

  test("借方输入自动清空贷方", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    const [d1, c1] = screen.getAllByPlaceholderText("0.00");
    fireEvent.change(c1, { target: { value: "50" } });
    fireEvent.change(d1, { target: { value: "30" } });
    expect(c1.value).toBe("");
  });

  test("金额输入过滤非数字", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    const [d1] = screen.getAllByPlaceholderText("0.00");
    fireEvent.change(d1, { target: { value: "12ab3.4" } });
    expect(d1.value).toBe("123.4");
  });

  test("添加分录按钮增加行", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByText("＋ 添加分录"));
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  test("删除分录保留至少一行", () => {
    const { container } = render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    const del = container.querySelectorAll('button[title="删除本行"]');
    fireEvent.click(del[0]);
    expect(container.querySelectorAll('button[title="删除本行"]').length).toBe(1);
  });

  test("合计金额正确汇总", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    const [d1, , d2] = screen.getAllByPlaceholderText("0.00");
    fireEvent.change(d1, { target: { value: "100.50" } });
    fireEvent.change(d2, { target: { value: "0.50" } });
    // 借方合计 101.00（两行合计）
    expect(screen.getAllByText("101.00").length).toBeGreaterThan(0);
  });

  test("空凭证时保存按钮禁用", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("保存凭证")).toBeDisabled();
  });

  test("不平衡时保存按钮禁用", () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[0], { target: { value: "10" } });
    expect(screen.getByText("保存凭证")).toBeDisabled();
  });

  test("保存成功提交正确载荷并回调", async () => {
    const onSaved = jest.fn();
    render(<VoucherEditor onSaved={onSaved} onCancel={() => {}} />);
    // 行1：银行存款 借 100
    fireEvent.focus(screen.getAllByPlaceholderText("输入编码/名称/拼音首字母")[0]);
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByText("银行存款"));
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[0], { target: { value: "100" } });
    // 行2：办公费 贷 100
    fireEvent.focus(screen.getAllByPlaceholderText("输入编码/名称/拼音首字母")[1]);
    await waitFor(() => expect(screen.getByText("办公费")).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByText("办公费"));
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[3], { target: { value: "100" } });
    fireEvent.click(screen.getByText("保存凭证"));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const call = global.fetch.mock.calls.find(([u]) => String(u).endsWith("/api/vouchers"));
    const body = JSON.parse(call[1].body);
    expect(body.entries).toHaveLength(2);
    expect(body.entries[0]).toMatchObject({ account_id: 1, debit: 100, credit: 0 });
    expect(body.entries[1]).toMatchObject({ account_id: 2, debit: 0, credit: 100 });
  });

  test("编辑模式预填凭证内容", () => {
    render(
      <VoucherEditor
        voucher={{
          id: 5,
          date: "2026-01-15",
          vtype: "记",
          entries: [
            {
              id: 1, account_id: 1, account_code: "1002", account_name: "银行存款",
              summary: "销售", debit: 100, credit: 0, quantity: 0, unit: "",
            },
            {
              id: 2, account_id: 2, account_code: "5001", account_name: "主营业务收入",
              summary: "销售", debit: 0, credit: 100, quantity: 0, unit: "",
            },
          ],
        }}
        onSaved={() => {}}
        onCancel={() => {}}
      />
    );
    expect(screen.getByDisplayValue("1002 银行存款")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("销售")).toHaveLength(2);
    expect(screen.getByText("✓ 借贷平衡")).toBeInTheDocument();
  });

  test("后端校验失败展示错误信息", async () => {
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/api/vouchers/suggest")) return Promise.resolve(okJson(SUGGEST));
      if (u.includes("/api/settings/voucher-types")) return Promise.resolve(okJson([]));
      return Promise.resolve({
        ok: false,
        status: 400,
        json: async () => ({ detail: "科目 5602 不是末级科目，不能记账" }),
      });
    });
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    fireEvent.focus(screen.getAllByPlaceholderText("输入编码/名称/拼音首字母")[0]);
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByText("银行存款"));
    fireEvent.focus(screen.getAllByPlaceholderText("输入编码/名称/拼音首字母")[1]);
    await waitFor(() => expect(screen.getByText("办公费")).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByText("办公费"));
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[0], { target: { value: "1" } });
    fireEvent.change(screen.getAllByPlaceholderText("0.00")[3], { target: { value: "1" } });
    fireEvent.click(screen.getByText("保存凭证"));
    await waitFor(() =>
      expect(screen.getByText(/不是末级科目/)).toBeInTheDocument()
    );
  });

  test("摘要输入展示历史摘要补全", async () => {
    render(<VoucherEditor onSaved={() => {}} onCancel={() => {}} />);
    fireEvent.focus(screen.getAllByPlaceholderText("摘要")[0]);
    await waitFor(() => expect(screen.getByText("销售商品")).toBeInTheDocument());
    expect(screen.getByText("支付办公费")).toBeInTheDocument();
  });
});
