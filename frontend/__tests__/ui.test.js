/**
 * components/ui.js 组件测试
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { Alert, Badge, Empty, Field, Modal, Money, Tabs } from "@/components/ui";

describe("Modal", () => {
  test("open=false 时不渲染", () => {
    render(<Modal open={false} title="标题">内容</Modal>);
    expect(screen.queryByText("标题")).not.toBeInTheDocument();
  });

  test("open=true 时渲染标题与内容", () => {
    render(<Modal open title="新增凭证">表单内容</Modal>);
    expect(screen.getByText("新增凭证")).toBeInTheDocument();
    expect(screen.getByText("表单内容")).toBeInTheDocument();
  });

  test("点击右上角关闭触发 onClose", () => {
    const onClose = jest.fn();
    render(<Modal open title="标题" onClose={onClose}>x</Modal>);
    fireEvent.click(screen.getByText("×"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("按 Escape 关闭", () => {
    const onClose = jest.fn();
    render(<Modal open title="标题" onClose={onClose}>x</Modal>);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("wide 样式生效", () => {
    const { container } = render(<Modal open wide title="宽">x</Modal>);
    expect(container.querySelector(".max-w-5xl")).toBeInTheDocument();
  });
});

describe("Tabs", () => {
  const tabs = [
    { key: "a", label: "总账" },
    { key: "b", label: "明细账" },
  ];

  test("渲染全部标签", () => {
    render(<Tabs tabs={tabs} active="a" onChange={() => {}} />);
    expect(screen.getByText("总账")).toBeInTheDocument();
    expect(screen.getByText("明细账")).toBeInTheDocument();
  });

  test("激活标签有高亮样式", () => {
    render(<Tabs tabs={tabs} active="a" onChange={() => {}} />);
    expect(screen.getByText("总账").className).toContain("tab-active");
    expect(screen.getByText("明细账").className).toContain("tab-idle");
  });

  test("点击切换回调", () => {
    const onChange = jest.fn();
    render(<Tabs tabs={tabs} active="a" onChange={onChange} />);
    fireEvent.click(screen.getByText("明细账"));
    expect(onChange).toHaveBeenCalledWith("b");
  });
});

describe("Money", () => {
  test("格式化两位小数", () => {
    render(<Money v={1234.5} />);
    expect(screen.getByText("1,234.50")).toBeInTheDocument();
  });

  test("空值显示破折号", () => {
    render(<Money v={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  test("dim 模式下 0 显示灰色", () => {
    const { container } = render(<Money v={0} dim />);
    expect(container.querySelector(".text-slate-300")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  test("默认颜色", () => {
    render(<Badge>已记账</Badge>);
    expect(screen.getByText("已记账").className).toContain("bg-slate-100");
  });

  test("green 颜色", () => {
    render(<Badge color="green">有效</Badge>);
    expect(screen.getByText("有效").className).toContain("bg-emerald-100");
  });

  test("red 颜色", () => {
    render(<Badge color="red">已作废</Badge>);
    expect(screen.getByText("已作废").className).toContain("bg-rose-100");
  });
});

describe("Alert", () => {
  test("error 类型样式", () => {
    render(<Alert>出错了</Alert>);
    expect(screen.getByText("出错了").parentElement.className).toContain("bg-rose-50");
  });

  test("success 类型样式", () => {
    render(<Alert type="success">成功</Alert>);
    expect(screen.getByText("成功").parentElement.className).toContain("bg-emerald-50");
  });

  test("onClose 触发", () => {
    const onClose = jest.fn();
    render(<Alert onClose={onClose}>x</Alert>);
    fireEvent.click(screen.getByText("✕"));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Empty / Field", () => {
  test("Empty 默认文案", () => {
    render(<Empty />);
    expect(screen.getByText("暂无数据")).toBeInTheDocument();
  });

  test("Empty 自定义文案", () => {
    render(<Empty text="该期间无凭证" />);
    expect(screen.getByText("该期间无凭证")).toBeInTheDocument();
  });

  test("Field 渲染标签", () => {
    render(<Field label="凭证日期"><input /></Field>);
    expect(screen.getByText("凭证日期")).toBeInTheDocument();
  });
});
