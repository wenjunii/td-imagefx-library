uniform float uMix;
uniform float uTiltX;
uniform float uTiltY;
uniform float uPerspective;
uniform float uZoom;
uniform vec2 uCenter;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 point = uv - uCenter;
    float depth = 1.0 + (point.x * sin(uTiltY) - point.y * sin(uTiltX)) * uPerspective;
    vec2 projected = vec2(point.x * cos(uTiltY), point.y * cos(uTiltX));
    projected = projected / max(abs(depth), 0.0001) / max(uZoom, 0.0001) + uCenter;
    bool inside = all(greaterThanEqual(projected, vec2(0.0))) && all(lessThanEqual(projected, vec2(1.0))) && depth > 0.0;
    vec4 warped = inside ? texture(sTD2DInputs[0], projected) : vec4(0.0);
    fragColor = TDOutputSwizzle(mix(source, warped, clamp(uMix, 0.0, 1.0)));
}
