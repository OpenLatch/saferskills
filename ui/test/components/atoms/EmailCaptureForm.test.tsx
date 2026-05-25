import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { axe } from 'vitest-axe';
import EmailCaptureForm from '../../../components/atoms/EmailCaptureForm';

describe('EmailCaptureForm', () => {
  it('renders email field and submit button', () => {
    render(<EmailCaptureForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /notify me/i })).toBeEnabled();
  });

  it('is accessible (vitest-axe smoke)', async () => {
    const { container } = render(<EmailCaptureForm />);
    const results = await axe(container);
    expect(results.violations).toHaveLength(0);
  });
});
