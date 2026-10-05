import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { TradingViewWidget } from '../TradingViewWidget';

function renderWidget() {
  return render(
    <UiLanguageProvider>
      <TradingViewWidget widget="technical-analysis" config={{ symbol: 'SSE:600519' }} height={300} />
    </UiLanguageProvider>,
  );
}

describe('TradingViewWidget', () => {
  it('injects the embed script with the widget config', () => {
    renderWidget();
    const container = screen.getByTestId('tradingview-technical-analysis');
    const script = container.querySelector('script');
    expect(script?.src).toBe('https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js');
    const config = JSON.parse(script?.text ?? '{}');
    expect(config).toMatchObject({ symbol: 'SSE:600519', height: 300, width: '100%', locale: 'en' });
    expect(['light', 'dark']).toContain(config.colorTheme);
    expect(screen.getByText('Loading TradingView widget…')).toBeInTheDocument();
  });

  it('shows a fallback message when the script fails to load', () => {
    renderWidget();
    const script = screen.getByTestId('tradingview-technical-analysis').querySelector('script');
    act(() => {
      fireEvent.error(script as HTMLScriptElement);
    });
    expect(screen.getByRole('status')).toHaveTextContent('The TradingView widget failed to load');
  });

  it('hides the placeholder once the widget iframe appears', async () => {
    renderWidget();
    const container = screen.getByTestId('tradingview-technical-analysis');
    await act(async () => {
      container.appendChild(document.createElement('iframe'));
      await Promise.resolve();
    });
    expect(screen.queryByText('Loading TradingView widget…')).not.toBeInTheDocument();
  });
});
