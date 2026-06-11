import type { Story } from '@ladle/react'
import PageRidge from '../../components/atoms/PageRidge'

export const Contour: Story = () => <PageRidge variant="contour" label="— /ABOUT —" />
export const Mesh: Story = () => <PageRidge variant="mesh" label="— /METHODOLOGY —" />
export const Swell: Story = () => <PageRidge variant="swell" label="— /DOCS —" />
export const Circuit: Story = () => <PageRidge variant="circuit" label="— /AGENTS/SCAN —" />

export const NoLabel: Story = () => <PageRidge variant="contour" />
